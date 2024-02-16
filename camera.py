import argparse
import asyncio
import json
import logging
import os
import ssl
import time

import cv2
import mediapipe as mp
from aiohttp import web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.rtcrtpsender import RTCRtpSender

ROOT = os.path.dirname(__file__)
# logging.basicConfig(level=logging.DEBUG)
# logger = logging.getLogger(__name__)

i = 0
relay = None
webcam = None

mpPose = mp.solutions.pose
pose = mpPose.Pose()
mpDraw = mp.solutions.drawing_utils

jump_started = False
repetitions_count = 0
pTime = 0


async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    # Регистрируем WebSocket соединение для дальнейшего использования
    request.app['websockets'].add(ws)

    try:
        async for msg in ws:
            # Пример обработки входящего сообщения
            if msg.type == web.WSMsgType.TEXT:
                if msg.data == 'close':
                    await ws.close()
            elif msg.type == web.WSMsgType.ERROR:
                print('WebSocket connection closed with exception %s' % ws.exception())
    finally:
        # Удаляем WebSocket соединение из регистрации
        request.app['websockets'].remove(ws)

    return ws


async def send_repetitions_count(repetitions_count):
    message = json.dumps({'type': 'repetitions_count', 'data': repetitions_count})
    for ws in app['websockets']:
        await ws.send_str(message)


def force_codec(pc, sender, forced_codec):
    kind = forced_codec.split("/")[0]
    codecs = RTCRtpSender.getCapabilities(kind).codecs
    transceiver = next(t for t in pc.getTransceivers() if t.sender == sender)
    transceiver.setCodecPreferences(
        [codec for codec in codecs if codec.mimeType == forced_codec]
    )


def process_image(frame):
    global jump_started, repetitions_count, pTime

    # Ваша обработка изображения с использованием Mediapipe
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
            print("Выполнен прыжок:", repetitions_count)
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
    # logger.debug("Received request for index page")
    content = open(os.path.join(ROOT, "index.html"), "r").read()
    return web.Response(content_type="text/html", text=content)


async def javascript(request):
    content = open(os.path.join(ROOT, "client.js"), "r").read()
    return web.Response(content_type="application/javascript", text=content)


async def offer(request):
    # logger.debug("Received offer request")
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])
    # logger.debug("Received offer: %s", offer)
    print("OFFER ", offer)

    pc = RTCPeerConnection()
    pcs.add(pc)
    # logger.debug("Created RTCPeerConnection")

    print("RTC PEER Connection ", pcs)

    @pc.on("track")
    async def on_track(track):
        print("Received track:", track.kind)

        if track.kind == "video":
            print("Received video track")
            # Создаем окно для отображения
            #cv2.namedWindow("Live Video", cv2.WINDOW_NORMAL)
            # Обрабатываем каждый кадр видео
            while True:
                frame = await track.recv()
                print("FRAME ", frame)
                # Конвертируем кадр из изображения aiortc в массив NumPy
                image = frame.to_ndarray(format="bgr24")
                processed_image, fps, repetitions_count = process_image(image)
                send_repetitions_count(repetitions_count)
                print("Repetitions_count", repetitions_count)
                # Отображаем обработанный кадр

                #cv2.imshow("Live Video", processed_image)
                # Задержка для обработки событий окна

                #if cv2.waitKey(1) & 0xFF == ord('q'):
                    #break
                # Сохраняем кадр в файл

                # Добавьте здесь дополнительную логику обработки, если необходимо

        # Для аудиотреков или других типов треков может быть добавлена дополнительная логика

    await pc.setRemoteDescription(offer)

    # Создание ответа для отправки клиенту
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )


pcs = set()


async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WebRTC webcam demo")
    parser.add_argument("--cert-file", help="SSL certificate file (for HTTPS)")
    parser.add_argument("--key-file", help="SSL key file (for HTTPS)")
    parser.add_argument("--play-from", help="Read the media from a file and sent it.")
    parser.add_argument(
        "--play-without-decoding",
        help=(
            "Read the media without decoding it (experimental). "
            "For now it only works with an MPEGTS container with only H.264 video."
        ),
        action="store_true",
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host for HTTP server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port for HTTP server (default: 8080)"
    )
    parser.add_argument("--verbose", "-v", action="count")
    parser.add_argument(
        "--audio-codec", help="Force a specific audio codec (e.g. audio/opus)"
    )
    parser.add_argument(
        "--video-codec", help="Force a specific video codec (e.g. video/H264)"
    )

    args = parser.parse_args()

    # if args.verbose:
    #     logging.basicConfig(level=logging.DEBUG)
    # else:
    #     logging.basicConfig(level=logging.INFO)

    if args.cert_file:
        ssl_context = ssl.SSLContext()
        ssl_context.load_cert_chain(args.cert_file, args.key_file)
    else:
        ssl_context = None


    async def on_startup(app):
        app['websockets'] = set()


    app = web.Application()
    app.on_shutdown.append(on_shutdown)
    app.router.add_get("/", index)
    app.router.add_get("/client.js", javascript)
    app.router.add_post("/offer", offer)
    #app.router.add_get('/ws', websocket_handler)


    async def test_ws(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_str("Test message")
        await ws.close()
        return ws


    # Добавьте этот маршрут в инициализацию сервера для тестирования
    app.router.add_get('/ws', test_ws)
    # Регистрация маршрута WebSocket
    web.run_app(app, host=args.host, port=args.port, ssl_context=ssl_context)
