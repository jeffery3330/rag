document.addEventListener("DOMContentLoaded", function () {
    fetchFiles();
});

function fetchFiles() {
    fetch('/files')
        .then(response => response.json())
        .then(files => {
            const fileList = document.getElementById('file-list');
            fileList.innerHTML = '';
            files.forEach(file => {
                const li = document.createElement('li');
                li.textContent = file;
                li.addEventListener('click', () => downloadFile(file));
                fileList.appendChild(li);
            });
        })
        .catch(error => console.error('Error fetching files:', error));
}

function downloadFile(filename) {
    const link = document.createElement('a');
    link.href = `/download/${filename}`;
    link.download = filename;
    link.click();
}

let mediaRecorder;
let audioChunks = [];
let isRecording = false;

async function sendMessage(inputElement) {
    if (event.key !== 'Enter') return;

    const userMessage = inputElement.value.trim();
    if (userMessage === '') return;

    appendUserMessage(userMessage);
    inputElement.value = '';

    elements = await appendBotMessage(userMessage);
}

function appendUserMessage(message) {
    const chatBox = document.getElementById('chat-box');
    const messageElement = document.createElement('div');
    messageElement.className = 'message user-message';
    messageElement.textContent = message;
    chatBox.appendChild(messageElement);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function appendBotMessage(userMessage) {
    const chatBox = document.getElementById('chat-box');

    const messageElement = document.createElement('div');
    messageElement.className = 'message bot-response';

    const spinner = document.createElement('div');
    spinner.className = 'spinner';
    messageElement.appendChild(spinner);

    const referencesElement = document.createElement('div');
    referencesElement.className = 'message bot-response-references';

    messageElement.addEventListener('click', function(){
        if (referencesElement.style.maxHeight){
            referencesElement.style.maxHeight = null;
        } else {
            referencesElement.style.maxHeight = referencesElement.scrollHeight + "px";
        }
    });

    chatBox.appendChild(messageElement);
    chatBox.appendChild(referencesElement);
    chatBox.scrollTop = chatBox.scrollHeight;

    var socket = io();

    const requestData = {
        message: userMessage
    };

    socket.emit('request', requestData);

    socket.on('response', function(data) {
        messageElement.textContent = data.message;
        referencesElement.innerHTML = data.references;
        chatBox.scrollTop = chatBox.scrollHeight;
    });
}

async function startRecording() {
    const recordButton = document.getElementById('record-button');

    // Get microphone permission
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            await navigator.mediaDevices.getUserMedia({ audio: true })
            .then(async (stream) => {
                mediaRecorder = new MediaRecorder(stream);
            })
            .catch((err) => {
                console.error('Error accessing media devices.', err);
            });
    } else {
        console.error('getUserMedia is not supported in this browser.');
    }

    mediaRecorder.start();

    mediaRecorder.ondataavailable = (event) => {
        audioChunks.push(event.data);
    };
    
    mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunks, { type: mediaRecorder.mimeType });

        const audioFile = new File([audioBlob], 'recording.webm', { type: mediaRecorder.mimeType });
        const formData = new FormData();
        formData.append("audio", audioFile);

        fetch('/upload', {
            method: "POST",
            body: formData
        }).then(response => 
            response.text()
        ).then(data => {
            const input = document.getElementById('user-input')
            input.value = input.value + data
        });

        audioChunks = [];
    };
};

async function stopRecording() {
    mediaRecorder.stop();
}

async function toggleRecording() {
    const recordButton = document.getElementById('record-button');
    if (isRecording) {
        await stopRecording();
        recordButton.textContent = 'Record';
        recordButton.classList.remove('stop');
    } else {
        await startRecording();
        recordButton.textContent = 'Stop';
        recordButton.classList.add('stop');
    }
    isRecording = !isRecording;
}