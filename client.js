function negotiate() {
    return pc.createOffer().then((offer) => {
        return pc.setLocalDescription(offer);
    }).then(() => {
        // Ожидание завершения сбора ICE кандидатов
        return new Promise((resolve) => {
            if (pc.iceGatheringState === 'complete') {
                resolve();
            } else {
                const checkState = () => {
                    if (pc.iceGatheringState === 'complete') {
                        pc.removeEventListener('icegatheringstatechange', checkState);
                        resolve();
                    }
                };
                pc.addEventListener('icegatheringstatechange', checkState);
            }
        });
    }).then(() => {
        var offer = pc.localDescription;
        // Отправляем предложение (offer) на сервер
        return fetch('/offer', {
            body: JSON.stringify({
                sdp: offer.sdp,
                type: offer.type,
            }),
            headers: {
                'Content-Type': 'application/json'
            },
            method: 'POST'
        });
    }).then((response) => {
        return response.json();
    }).then((answer) => {
        return pc.setRemoteDescription(answer);
    }).catch((e) => {
        alert(e);
    });
}

function start() {
    var config = {
        sdpSemantics: 'unified-plan'
    };

    if (document.getElementById('use-stun').checked) {
        config.iceServers = [{urls: ['stun:stun.l.google.com:19302']}];
    }

    pc = new RTCPeerConnection(config);

    pc.ontrack = (evt) => {
        if (evt.track.kind === 'video') {
            document.getElementById('video').srcObject = evt.streams[0];
        }
    };

    pc.onconnectionstatechange = (event) => {
        //console.log(Connection, state, change: ${pc.connectionState})

        if (pc.connectionState === 'connected') {
            console.log("Connection established.");
        }
    };

    // Запрос доступа к камере и микрофону
    navigator.mediaDevices.getUserMedia({video: true, audio: true}).then((stream) => {
        // Получаем локальный видеопоток и отображаем его
        document.getElementById('localVideo').srcObject = stream;

        stream.getTracks().forEach((track) => {
            pc.addTrack(track, stream);
        });

        document.getElementById('start').style.display = 'none';
        document.getElementById('stop').style.display = 'inline-block';
        negotiate(); // Запускаем процесс установки соединения
    }).catch((err) => {
        console.error('Failed to get media: ', err);
        alert('Ошибка: не удалось получить доступ к камере и микрофону!');
    });
}

