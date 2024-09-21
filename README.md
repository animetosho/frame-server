**Script to serve an image from a single frame video via HTTP**

This is a relatively simple Python script which can render the first frame of a given video file as a PNG/JPEG/WEBP image. It can also optionally overlay a WEBP file on top of the image, which can be useful for subtitle rendering, as well as scale images to a custom resolution.

This can be useful as video compression is often more efficient than the more widely accepted image formats in terms of size/quality ratio.

Anime Tosho stores screenshots of videos by dumping out and storing I frames. Corresponding subtitle frames are rendered out as transparent WEBP images and stored alongside the I frames. Actual rendering to PNG/JPEG happens dynamically, using this script, which converts the single frame video into a commonly supported image format, optionally with a subtitle overlay. This stored I frame is often several times smaller than a lossless PNG version.  
Note that this script is designed for AT's use, and very likely needs to be modified if you intend to use it. It is provided here mostly for interested parties, rather than something I expect to actually be useful to anyone else.

## Rationale

Generating screenshots of videos can be useful for providing a quick idea of what a video contains, as well as be used for an indication of encode quality or quality comparisons\* between different versions of the same video.

The obvious solution to this problem is to render some frames of the video and save them as a lossless format, usually as PNG images, which can then be displayed in a browser. Despite PNG’s large size, relative to something lossy like JPEG, it is necessary to have a lossless image for quality evaluation/comparison purposes.

Unfortunately, as alluded to, PNG images are quite large, and storing many such images can require a lot of disk space. Using a more efficient format, such as WEBP, may be possible, however support for the format is relatively low. One could possibly go further and try using single frame videos, such as H.264 lossless, BPG or similar, but support for these (assuming one embeds these in an MP4 container and serves it back via HTML5’s video element) in web browsers is still likely poor.

However, we can actually get even smaller sizes than using a highly efficient lossless image format: simply extract a frame from the video file itself. This is much more efficient as video files are often lossy, so don’t have the same amount of overhead of a lossless format, yet we introduce no further loss by doing this. In other words, we get a lossless image, at a lossy size!

Anime Tosho uses this idea to reduce the amount of storage required to store screenshots, and this script provides the bridge to enable website visitors to see the stored frames as viewable PNG images.

One caveat of this approach is that ‘soft’ (dynamically rendered) subtitles won’t be shown, as they are not a part of the original video stream. We can solve this by rendering subtitle overlays separately as a transparent WEBP, then overlaying during the render process. These transparent WEBP images are often small, as subtitle frames are usually mostly transparent, and otherwise usually compress well. Dynamically rendering subtitles like this also enables subtitles from different streams to be rendered, or even have subtitles turned off, as opposed to be stuck with what you originally rendered into the PNG.  
An alternative approach may be to render the original subtitle file onto the image, rather than rendering to an intermediary WEBP file. I have chosen not to employ this strategy as the complexity of such is likely not worth the small space penalty for pre-rendered subtitles.

Another useful feature of this script is the ability to dynamically scale images for thumbnails, which would otherwise require storing a second, scaled down, copy of the image. Not only does this save a small amount of space, it enables different resolutions to be rendered, which can be useful for targeting high DPI displays.

\* A downside of this approach of extracting video frames is that only I frames can be extracted (a screenshot of a P/B frame cannot be done). As only I frames can be shown, some may question whether this provides an indicative representation of the video’s quality. On the other hand, this approach ensures comparisons are always done using the same frame type, e.g. you won’t ever try to compare an I frame of one video against a B frame of another. So it’s hard to say whether this is a good or bad idea, though I’d comment that comparing video quality using still images has its limitations, and is more of an issue than what frame type was selected.

## Speed Concerns

Obviously performing on-the-fly conversion, particularly with higher resolution images, is going to be significantly slower than a server sending out static assets. One justification is that storage servers tend to have plenty of otherwise unused CPU resources available, so we trade some of that for a significant reduction in storage space, which is often a limiting factor.

However, if only a small number of images are frequently served, caching can significantly reduce additional load caused by on-the-fly conversion, and this script is intended to run behind a caching system (such as nginx’s [uwsgi cache](http://nginx.org/en/docs/http/ngx_http_uwsgi_module.html#uwsgi_cache)).

## Setup

Script is designed to run under uWSGI. A [sample INI configuration is supplied](sample-uwsgi.ini).

It should operate under Python 2. Probably works under Python 3. It requires the [PyAV](https://github.com/mikeboers/PyAV), [PIL](https://python-pillow.org/) and [fpnge](https://github.com/animetosho/python-fpnge) modules.

You’ll also likely need a webserver that can interact with uWSGI, such as nginx. It is strongly recommended that a caching layer be placed in front, e.g. nginx’s uwsgi cache or a HTTP caching proxy, to reduce load. A [sample nginx configuration is also supplied](sample-nginx.conf).

Finally, you’ll need to edit [the script](app.py) to configure the location that files are stored, and the desired URL mapping to these files.

**Note: I do not intend to provide support for this script, as it is intended primarily for informative purposes**

## Script Usage

Images are converted and outputted when the application receives a request.

Supported URL parameters are:

* `w` and `h`: width and height, respectively, to rescale the image to; useful for thumbnails
* `s`: numerical index of the subtitle track to render on the image

In addition, the extension supplied (e.g. `.png`) determines the image format to output as.

## Creating Frame Dumps

The process used by Anime Tosho’s script to produce compatible images is perhaps a little crude, but a brief explanation is provided below nonetheless.

A frame from a video can be extracted using the [ffmpeg utility](http://ffmpeg.org/), with a command like the following.

```bash
ffmpeg -y -fflags genpts -noaccurate_seek -ss [target_time] -i [input_file] -map_chapters -1 -map_metadata -1 -an -sn -dn -vcodec copy -frames 1 -f matroska [output_file]
```

The result should be a single frame MKV video file containing the last I frame before the target time specified.

Note that we disregard videos which have more than one video stream (which is occurs very rarely in practice, and one isn’t really sure how such videos should be handled anyway).

Subtitles are rendered using [VapourSynth](http://www.vapoursynth.com/), using a script like the following:

```python
## set these variables from somewhere
width=$video_width
height=$video_height
length=$video_length  # in ms, used for rendering dummy video, just needs to be long enough for all subtitle snapshots to be taken
imagesub=$is_image_subtitle # True for PGS/VOB subtitles
source=$subtitle_file
fontdir=$fontdir # fonts for ASS subtitles
charset=$subtitle_charset # ignored for image-based subtitles
times=[$time1, $time2 ...] # times in ms
output=$output

import vapoursynth as vs
import operator
core = vs.get_core()
b = core.std.BlankClip(width=width, height=height, format=vs.RGB24, length=length, fpsnum=1000, fpsden=1)

if imagesub:
    rgb = core.sub.ImageFile(b, file=source, blend=False)
    alpha = core.std.PropToClip(rgb)
else:
    [rgb, alpha] = core.sub.TextFile(b, file=source, fontdir=fontdir, charset=charset, blend=False)

if rgb.width != width or rgb.height != height:
    rgb = core.resize.Spline36(rgb, width=width, height=height)
    alpha = core.resize.Spline36(alpha, width=width, height=height)

alpha = core.std.Invert(alpha)

from functools import reduce
Srgb = reduce(operator.add, map(lambda x: rgb[x], times))
Salpha = reduce(operator.add, map(lambda x: alpha[x], times))

core.imwri.Write(Srgb, "PNG", output, alpha=Salpha, compression_type="None").set_output()
```

After PNGs are rendered, the [is\_image\_transparent](https://github.com/animetosho/is_image_transparent) tool is used to discard fully transparent frames, then [cwebp](https://developers.google.com/speed/webp/docs/cwebp) is used to convert the PNGs into the final WEBP format.

