## Render Post v1.13.1

**Fix:** on some Windows PCs, enhancing with a fal model failed right at the end with a
certificate error ("CERTIFICATE_VERIFY_FAILED ... unable to get local issuer certificate").
The prompt was written and the image was generated and paid for on fal, but RenderPost
couldn't download the result.

The cause was a mismatch between two trust stores. fal's API calls verify certificates against
a certificate bundle shipped inside the app, so they always worked. The download used Windows'
own certificate store instead, and Windows only fetches a missing root certificate when a
browser asks for it, never when an app like RenderPost does. All of RenderPost's downloads now
trust the bundled certificates as well as Windows' store. Certificates added by a work network
or antivirus keep working.

The fal result download also now retries a dropped connection instead of throwing away an image
you already paid for. If a certificate check still fails, the error now says what to try
(VPN, antivirus web shield or a work network that inspects HTTPS) instead of the raw message.
