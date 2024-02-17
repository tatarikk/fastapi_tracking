let pc; // Переменная для хранения объекта RTCPeerConnection

function negotiate() {
    console.log('WebRTC Connection state: connecting'); // Добавляем лог для отладки
    return pc.createOffer().then((offer) => {
        return pc.setLocalDescription(offer);
    }).then(() => {
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
        console.log('Local offer:', offer); // Добавляем лог для отладки
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
        console.log('Answer from server:', answer); // Добавляем лог для отладки
        return pc.setRemoteDescription(answer).then(() => {
            // Обновляем переменную repetitions_count при получении ответа от сервера
            document.getElementById('repetitions_count').innerText = answer.repetitions_count;
        });
    }).catch((e) => {
        console.error('Negotiation error:', e); // Добавляем лог для отладки
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
        console.log('WebRTC Connection state:', pc.connectionState); // Добавляем лог для отладки
        if (pc.connectionState === 'connected') {
            console.log("Connection established.");
        }
    };

    // WebSocket соединение
    const ws = new WebSocket((window.location.protocol === 'https:' ? 'wss://' : 'ws://') + window.location.host + '/ws');
    console.log('WebSocket Connection state: connecting'); // Добавляем лог для отладки
    console.log('WebSocket connection:', ws.url); // Добавляем лог для отладки
    ws.onmessage = function (event) {
        const data = JSON.parse(event.data);
        console.log('Data received from server:', data); // Добавляем лог для отладки
        if (data.repetitions_count !== undefined) {
            // Обновляем переменную repetitions_count при получении сообщения от сервера
            document.getElementById('repetitions_count').innerText = data.repetitions_count;
        }
    };
    navigator.mediaDevices.getUserMedia({video: true, audio: true}).then((stream) => {
        document.getElementById('localVideo').srcObject = stream;

        stream.getTracks().forEach((track) => {
            pc.addTrack(track, stream);
        });

        document.getElementById('start').style.display = 'none';
        document.getElementById('stop').style.display = 'inline-block';
        negotiate();
    }).catch((err) => {
        console.error('Failed to get media: ', err);
        alert('Ошибка: не удалось получить доступ к камере и микрофону!');
    });
}
