"""Local Restapi used for React frontend"""
import io
import uvicorn
from fastapi import FastAPI, Response

from poker.tools.screen_operations import take_screenshot

app = FastAPI()


def local_restapi():

    @app.get("/screenshot_result")
    async def get_screenshot_result():
        screenshot = take_screenshot()
        image_bytes_io = io.BytesIO()
        screenshot.save(image_bytes_io, format="PNG")
        return Response(content=image_bytes_io.getvalue(), media_type="image/png")

    uvicorn.run(app, host="0.0.0.0", port=8005)
