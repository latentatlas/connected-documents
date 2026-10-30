Connected Documents — recorded review test build

This static directory contains an interactive review workflow and the historical
evidence page. It uses saved real NVIDIA Nemotron 3 Super responses from Nebius
Token Factory; no new inference request is made.

index.html: product overview
review.html: inspect, edit, confirm review, accept, download and undo
examples.html: read-only historical outcomes, including failures and corrections
testing.html: judge access and scope instructions
review-data.json: fictional source facts and original model responses
example-packets/: four unchanged historical accepted packets

Visitor edits remain in browser-tab memory until downloaded. Reloading clears
them. The application sends no visitor edits, analytics or API credentials.
The host can still keep its ordinary access logs.

For the local source distribution, run:
  python3 -B launch.py --judge --port 8984
from its root and open http://127.0.0.1:8984/ .

For static hosting, serve this directory at the site root. The publication
package adds downloads/connected-documents-source.zip; it is not nested inside
the source distribution itself. Local launch.py serves that route through a
verified manifest-only archive.

The live Python runtime and LIVE_SETUP.md are separate from this recorded mode.
No arbitrary upload, discovery of unknown document relationships, comparative
human benefit or independent model reliability is claimed.
