# Streaming and Recording (advanced)

For everyday use you only need the tracker page: full screen, camera on, done. But barehands was born on camera, and it composites beautifully.

## The two-page split

One scene, two views:

- **The tracker** (`stage.html`) owns your camera and physics. This is YOUR monitor.
- **The render page** (`stage.html?role=render`) is camera-free and truly transparent; it mirrors the scene from the server's state bus.

Drop the render URL into an OBS **browser source** over your camera source and OBS composites the glass with real alpha; the cards float over your actual video feed.

## The knobs (URL parameters on the render page)

- `&cursors=0`: hide the finger rings from the broadcast. Bare hands, maximum sorcery.
- `&ss=2` with a 3840×2160 browser source: 2× supersampled rendering, cards stay razor sharp when stretched.
- `&mirror=1`: if your OBS camera source is mirrored, this turns off the render page's default flip.
- `?portrait=1` on the **tracker**: vertical mode. The camera negotiates a 9:16 capture for Shorts/TikTok framing. Shape the tracker window tall to match, and use a 9:16 OBS canvas for the render source, with `&ss=3` instead of 2 (field-tested: the vertical composition needs the extra supersample; browser source at 3240×5760).
- `?res=WxH` on the **tracker**: capture resolution (default 1920x1080). Higher buys self-view sharpness, not tracking accuracy; lower (`1280x720`) buys fps on slow machines. Composes with `?portrait=1`, which swaps the dimensions.

The render page flips X by default because OBS shows cameras un-mirrored while the tracker works in selfie space: reach left, and the cards go left on the broadcast too.
