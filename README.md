# Xtream Samsung Playback Gateway

This service is designed for an IPTV account you are authorized to use. It keeps Xtream
credentials on the server and converts the provider stream to H.264/AAC HLS for a TV
browser.

## Render environment variables

Set these as Render Environment Variables (do not put them in the HTML):

XTREAM_SERVER=http://desyra.co:8080
XTREAM_USERNAME=your_username
XTREAM_PASSWORD=your_password
GATEWAY_KEY=choose-a-long-random-key
PUBLIC_BASE=https://YOUR-RENDER-SERVICE.onrender.com

The gateway key is optional but recommended.

## Deploy

Create a Render Web Service from this repository, use Docker, and deploy.

Health check:
GET /health

After deployment, test:
https://YOUR-SERVICE.onrender.com/health

## Important

Each playback request starts an FFmpeg HLS job. The provider account shown during
testing allowed one active connection, so keep only one stream active at a time.
VOD/Series may be expensive to transcode. A paid server with adequate CPU is
recommended for reliable playback.

The gateway is a technical playback layer; use it only with streams/content you are
authorized to access.
