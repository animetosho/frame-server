import vapoursynth as vs
#import logging
#logging.basicConfig(level=logging.DEBUG)
import os.path
import re
try:
	from urlparse import parse_qs
except ImportError:
	from urllib.parse import parse_qs


vs.core.num_threads = 1
vs.core.max_cache_size = 64 # MB

def to_int(s):
	try:
		return int(s)
	except:
		return 0

def application(env, start_response):
	### EDIT URL mapping here if desired
	m = re.search(r"/([0-9a-f]{3})([0-9a-f]{3})([0-9a-f]{2})_(\d+)\.(png|jpg)$", env.get('PATH_INFO'))
	if not m:
		start_response('404 Not Found', [('Content-Type', 'text/plain')])
		return ["Invalid request"]
	
	### EDIT File location mapping here if desired
	file_base = env.get('BASE_PATH') + m.group(1) + "/" + m.group(2) + "/" + m.group(3) + "_"
	ts = m.group(4)
	file = file_base + ts + ".mkv"
	
	if not os.path.isfile(file):
		start_response('404 Not Found', [('Content-Type', 'text/plain')])
		return ["File not found"]
	
	params = parse_qs(env.get('QUERY_STRING'))
	
	fmt = m.group(5).upper()
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
	frameNum = 0
	if 'f' in params:
		frameNum = to_int(params['f'][0])
		if frameNum < 0:
			frameNum = 0
	
	# do we want to render subtitles?
	sub = None
	if 's' in params:
		### EDIT Subtitle image location mapping here if desired
		subFile = file_base + str(to_int(params['s'][0])) + "_" + ts + ".webp"
		if os.path.isfile(subFile):
			sub = vs.core.bs.VideoSource(subFile, cachemode=0, threads=1, cachesize=48)
	
	codec_opts = None
	if 'x264' in params:
		x264_build = to_int(params['x264'][0])
		if x264_build < 151: # TODO: sending '157' can cause it to not be handled properly; since we only need this for 150 or lower, only do it for that (example '157': https://animetosho.org/view/commie-lupin-third-part-5-volume-3-bd-720p-aac.n1095684)
			codec_opts = ['x264_build', str(x264_build)]
	
	clip = None
	try:
		clip = vs.core.bs.VideoSource(file, cachemode=0, threads=1, cachesize=48, codec_opts=codec_opts)
		if clip.num_frames > 1:
			if frameNum >= clip.num_frames:
				frameNum = 0
			clip = clip[frameNum : frameNum+1]
		frame = clip.get_frame(0)
	except:
		pass
	if clip is None:
		start_response('500 Internal Server Error', [('Content-Type', 'text/plain')])
		return ["Failed to generate screenshot"]
	
	
	resizeArgs = {'clip': clip, 'format': vs.RGB24}
	sWidth = frame.width
	sHeight = frame.height
	
	# if colorimetry not defined, follow MPV's heuristics [https://wiki.x266.mov/docs/colorimetry/matrix]
	matrix_in = frame.props['_Matrix']
	if matrix_in == vs.MATRIX_UNSPECIFIED:
		matrix_in = vs.MATRIX_BT709 if sWidth >= 1280 or sHeight > 576 else vs.MATRIX_ST170_M
		resizeArgs['matrix_in'] = matrix_in
	if frame.props['_Primaries'] == vs.PRIMARIES_UNSPECIFIED:
		if matrix_in == vs.MATRIX_BT2020_NCL or matrix_in == vs.MATRIX_BT2020_CL:
			resizeArgs['primaries_in'] = vs.PRIMARIES_BT2020
		elif matrix_in == vs.MATRIX_BT709 or sWidth >= 1280 or sHeight > 576:
			resizeArgs['primaries_in'] = vs.PRIMARIES_BT709
		elif sHeight == 576:
			resizeArgs['primaries_in'] = vs.PRIMARIES_BT470_BG
		elif sHeight == 480 or sHeight == 488:
			resizeArgs['primaries_in'] = vs.PRIMARIES_ST170_M
		else:
			resizeArgs['primaries_in'] = vs.PRIMARIES_BT709
	if frame.props['_Transfer'] == vs.TRANSFER_UNSPECIFIED:
		resizeArgs['transfer_in'] = vs.TRANSFER_BT709
	
	# unfortunately, this doesn't pick up stream SAR, which may or may not be more accurate (BS prefers codec SAR over stream SAR)
	is_anamorphic = False
	if frame.props['_SARNum'] != 1 or frame.props['_SARDen'] != 1:
		is_anamorphic = True
		sRatio = float(frame.props['_SARNum']) / frame.props['_SARDen']
		if sRatio > 1:
			sWidth = int(round(frame.width*sRatio))
		else:
			sHeight = int(round(frame.height/sRatio))
	#  problematic clips: https://animetosho.org/file/maria-watches-over-us-s04e01-school-festival-shock-mkv.1037428 & https://animetosho.org/file/ironclad-dungeon-meshi-04-10bit-1080p-av1-mkv.1137705
	
	# TODO: how to detect Dolby Vision? pull AV_FRAME_DATA_DOVI_METADATA [https://ffmpeg.org/doxygen/trunk/structAVDOVIMetadata.html] side data?
	if 'ContentLightLevelMax' in frame.props and frame.props['ContentLightLevelMax'] >= 600 and 'MasteringDisplayWhitePointX' in frame.props and 'MasteringDisplayWhitePointY' in frame.props and 'MasteringDisplayPrimariesX' in frame.props and 'MasteringDisplayPrimariesY' in frame.props:
		# this might be HDR10
		# check for Rec2020 primaries
		primX = frame.props['MasteringDisplayPrimariesX']
		primY = frame.props['MasteringDisplayPrimariesY']
		if abs(frame.props['MasteringDisplayWhitePointX'] - 0.3127) < 0.0001 and abs(frame.props['MasteringDisplayWhitePointY'] - 0.3290) < 0.0001 and abs(primX[0] - 0.708) < 0.0001 and abs(primX[1] - 0.170) < 0.0001 and abs(primX[2] - 0.131) < 0.0001 and abs(primY[0] - 0.292) < 0.0001 and abs(primY[1] - 0.797) < 0.0001 and abs(primY[2] - 0.046) < 0.0001:
			# this is likely HDR10
			# TODO: convert to RGB48 instead?
			pass
			# TODO: check for HDR10+? likely requires source support to pull the AV_FRAME_DATA_DYNAMIC_HDR_PLUS [https://ffmpeg.org/doxygen/trunk/structAVDynamicHDRPlus.html] side info
	
	frame.close()
	
	# a problem with never upscaling is that for our srcset attribute, we go up to 384x288, so if the source video is smaller (unlikely these days), it'll get shrinked on the page
	# we could allow upscaling, but have to set a maximum dimension limit
	if reW and sWidth <= reW:
		reW = None
	if reH and sHeight <= reH:
		reH = None
	
	if is_anamorphic:
		resizeArgs['width'] = sWidth
		resizeArgs['height'] = sHeight
	
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
			clip = vs.core.resize.Bicubic(**resizeArgs)
			clip = vs.core.std.MaskedMerge(clip, sub, vs.core.std.PropToClip(sub))
			clip = vs.core.resize.Bicubic(clip, width=reW, height=reH)
		else:
			resizeArgs['width'] = reW
			resizeArgs['height'] = reH
			clip = vs.core.resize.Bicubic(**resizeArgs)
	else:
		clip = vs.core.resize.Bicubic(**resizeArgs)
		if sub:
			clip = vs.core.std.MaskedMerge(clip, sub, vs.core.std.PropToClip(sub))
	
	with clip.get_frame(0) as frame:
		qparam = 85 if fmt=="JPEG" else 4
		# TODO: pass color_trc to cICP
		data = vs.core.encodeframe.EncodeFrame(frame, fmt, param=qparam)
	
	headers.append(('Content-Length', str(len(data))))
	start_response('200 OK', headers)
	return [data]

