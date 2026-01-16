# BinaryKits ZPL Viewer (local)

This project uses the BinaryKits ZPL Viewer container for local ZPL previews.

## Run locally

- From this folder, run Docker Compose to start the viewer.
- The container exposes port 80.

Once running, open the viewer UI in your browser and paste a ZPL file from the tmp/ folder.

## Container image

- yipingruan/binarykits-zpl:latest

## Notes

- This is intended for local previewing. No label data leaves your network.
- We can wire the add-on to call this service directly once the add-on container is in place.
