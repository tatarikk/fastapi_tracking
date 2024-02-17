import argparse
import asyncio
import json
import os
import ssl
import time

import cv2
import mediapipe as mp
from aiohttp import web, WSMsgType
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.rtcrtpsender import RTCRtpSender

ROOT = os.path.dirname(__file__)

i = 0
relay = None
webcam = None

mpPose = mp.solutions.pose
pose = mpPose.Pose()
mpDraw = mp.solutions.drawing_utils

jump_started = False
repetitions_count = 0
pTime = 0

pcs = set()
pcs_ws = set()


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


def process_image(frame):
    global jump_started, repetitions_count, pTime

    imgRGB = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    results = pose.process(imgRGB)

    if results.pose_landmarks:
        point_30_y = results.pose_landmarks.landmark[30].y
        point_29_y = results.pose_landmarks.landmark[29].y
        point_25_y = results.pose_landmarks.landmark[25].y
        point_26_y = results.pose_landmarks.landmark[26].y
        point_15_y = results.pose_landmarks.landmark[15].y
        point_16_y = results.pose_landmarks.landmark[16].y
        point_13_y = results.pose_landmarks.landmark[13].y
        point_14_y = results.pose_landmarks.landmark[14].y

        if (
                (point_30_y < point_25_y or point_29_y < point_26_y) and
                (point_15_y < point_13_y and point_16_y < point_14_y) and
                not jump_started
        ):
            jump_started = True
            repetitions_count += 1
            #print("Выполнен прыжок:", repetitions_count)
        elif point_30_y >= point_25_y and point_29_y >= point_26_y:
            jump_started = False

        mpDraw.draw_landmarks(imgRGB, results.pose_landmarks, mpPose.POSE_CONNECTIONS)
        for id, lm in enumerate(results.pose_landmarks.landmark):
            h, w, c = imgRGB.shape
            cx, cy = int(lm.x * w), int(lm.y * h)
            cv2.circle(imgRGB, (int(cx), int(cy)), 10, (255, 0, 0), cv2.FILLED)

    cTime = time.time()
    fps = 1 / (cTime - pTime)
    pTime = cTime

    return imgRGB, fps, repetitions_count


async def index(request):
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pcs.add(pc)

    async def on_track(track):
        if track.kind == "video":
            while True:
                frame = await track.recv()
                image = frame.to_ndarray(format="bgr24")
                processed_image, fps, repetitions_count = process_image(image)
                print("REPETITIONS COUNT: ", repetitions_count)

                # Отправляем данные о repetitions_count через WebSocket всем клиентам
                for ws in pcs_ws:
                    await ws.send_json({"repetitions_count": repetitions_count})

    pc.on("track")(on_track)

    await pc.setRemoteDescription(offer)
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    pcs_ws.add(ws)
    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            if msg.data == 'close':
                await ws.close()
        elif msg.type == WSMsgType.ERROR:
            print('ws connection closed with exception %s' %
                  ws.exception())
    pcs_ws.remove(ws)
    print('websocket connection closed')

    return ws


async def on_shutdown(app):
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

    coros_ws = [ws.close() for ws in pcs_ws]
    await asyncio.gather(*coros_ws)
    pcs_ws.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument("--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port for HTTP server (default: 8080)")

    args = parser.parse_args()

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None

    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    app.router.add_get('/ws', websocket_handler)

    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)
