import av
import StringIO
import os.path
import re
from urlparse import parse_qs
from PIL import Image

def to_int(s):
	try:
		return int(s)
	except:
		return 0

def render_sub(image, sub):
	return Image.alpha_composite(image.convert("RGBA"), sub)

def application(env, start_response):
	
	#### EDIT THE FOLLOWING FOR URL MAPPING ####
	
	m = re.search(r"/([0-9a-f]{8}_\d+)\.(png|jpg|webp)$", env.get('PATH_INFO'))
	if not m:
		start_response('404 Not Found', [('Content-Type', 'text/plain')])
		return ["Invalid request"]
	
	file_base = "/storage/" + m.group(1) ## EDIT PATH
	file = file_base + ".mkv"
	
	if not os.path.isfile(file):
		start_response('404 Not Found', [('Content-Type', 'text/plain')])
		return ["File not found"]
	
	params = parse_qs(env.get('QUERY_STRING'))
	
	# determine desired output format
	fmt = m.group(2).upper()
	if fmt == "JPG":
		fmt = "JPEG"
	headers = [('Content-Type', 'image/' + fmt.lower())]
	
	# determine if resizing is wanted
	reW = None
	reH = None
	if 'w' in params:
		reW = to_int(params['w'][0])
		if reW < 1:
			reW = None
	if 'h' in params:
		reH = to_int(params['h'][0])
		if reH < 1:
			reH = None
	
	# do we want to render subtitles?
	sub = None
	if 's' in params:
		subFile = file_base + "_" + str(to_int(params['s'][0])) + ".webp" ## EDIT PATH
		if os.path.isfile(subFile):
			sub = Image.open(subFile).convert("RGBA")
	
	# open and render video
	container = av.open(file)
	video = next(s for s in container.streams if s.type == b'video')
	frame_found = False
	
	if video:
		output = StringIO.StringIO()
		for packet in container.demux(video):
			for frame in packet.decode():
				sWidth = frame.width
				sHeight = frame.height
				is_anamorphic = (video.sample_aspect_ratio != 0 and video.sample_aspect_ratio != 1)
				if is_anamorphic:
					if video.sample_aspect_ratio > 1:
						sWidth = int(round(frame.width*video.sample_aspect_ratio))
					else:
						sHeight = int(round(frame.height/video.sample_aspect_ratio))
				
				# if rendering subtitle, use that as a source of truth for dimensions
				# this is a workaround for PyAV not always detecting anamorphic content
				if sub and (sWidth != sub.width or sHeight != sub.height):
					sWidth = sub.width
					sHeight = sub.height
					is_anamorphic = True
				
				if reW or reH:
					# a problem with never upscaling is that for our srcset attribute, we go up to 384x288, so if the source video is smaller (unlikely these days), it'll get shrinked on the page
					# we could allow upscaling, but have to set a maximum dimension limit
					if sWidth <= reW:
						reW = None
					if sHeight <= reH:
						reH = None
				if reW or reH:
					sRatio = float(sWidth) / sHeight
					if reW and reH:
						tRatio = float(reW) / reH
						if tRatio > sRatio:
							reW = reH * sRatio
						elif tRatio < sRatio:
							reH = reW / sRatio
					elif reW:
						reH = reW / sRatio
					else:
						reW = reH * sRatio
					reW = int(round(reW))
					reH = int(round(reH))
					
					if sub:
						if is_anamorphic:
							image = frame.reformat(width=sWidth, height=sHeight, format='rgb24').to_image()
						else:
							image = frame.to_image()
						image = render_sub(image, sub).convert("RGB")
						image = image.resize((reW, reH), Image.BICUBIC)
					else:
						image = frame.reformat(width=reW, height=reH, format='rgb24').to_image()
				else:
					if is_anamorphic:
						image = frame.reformat(width=sWidth, height=sHeight, format='rgb24').to_image()
					else:
						image = frame.to_image()
					if sub:
						image = render_sub(image, sub)
					
				if fmt == "PNG":
					image.save(output, format="PNG", compress_level=3)
				elif fmt == "JPEG":
					image.save(output, format="JPEG", quality=85)
				elif fmt == "WEBP":
					image.save(output, format="WEBP", lossless=True)
				frame_found = True
				break
			if frame_found:
				break
	
	if not frame_found:
		start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
		return ["Failed to generate screenshot"]
	
	if sub:
		sub.close()
	
	data = output.getvalue()
	output.close()
	
	headers.append(('Content-Length', str(len(data))))
	start_response('200 OK', headers)
	return [data]

