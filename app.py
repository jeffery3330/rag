import faiss
import json
import numpy as np
import ollama
import os
import speech_recognition as sr
import subprocess
from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort
from flask_socketio import SocketIO, emit
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer

app = Flask(__name__)
socketio = SocketIO(app)

encoder = SentenceTransformer('all-distilroberta-v1')

app.config.from_pyfile('config.py')

# Ensure the folders exist
if not os.path.exists(app.config['UPLOAD_FOLDER']):
    os.makedirs(app.config['UPLOAD_FOLDER'])
if not os.path.exists(app.config['FILES_FOLDER']):
    os.makedirs(app.config['FILES_FOLDER'])

print("loading pdfs...")
filenames = next(os.walk(app.config['FILES_FOLDER']), (None, None, []))[2]

docs = [PyPDFLoader(app.config['FILES_FOLDER'] + filename).load() for filename in filenames]
docs_list = [item for sublist in docs for item in sublist]
text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
    chunk_size=500, chunk_overlap=250
)

doc_splits = text_splitter.split_documents(docs_list)

doc_splits_text = [doc.page_content for doc in doc_splits]

# Encode documents into vectors
document_vectors = encoder.encode(doc_splits_text)

# Create a FAISS index and add document vectors
index = faiss.IndexFlatL2(document_vectors.shape[1])  # L2 distance (Euclidean)
index.add(np.array(document_vectors))

print("pdfs loaded.")

def retrieve_context(query, top_k=7):
    query_vector = encoder.encode([query])[0]
    distances, indices = index.search(np.array([query_vector]), top_k)
    
    return [doc_splits[i] for i in indices[0]]

### Retrieval Grader

def check_relevance(question = None):
    
    docs = retrieve_context(question)
    
    doc_txt = docs[0].page_content
    
    system_prompt = """
        You are a grader assessing relevance of a retrieved document to a user question. 
        If the document contains keywords related to the user question, grade it as relevant. 
        It does not need to be a stringent test. 
        The goal is to filter out erroneous retrievals.
        Give a binary score 'relevant' or 'irrelevant' score to indicate whether the document is relevant to the question.
        Provide the binary score as a JSON with a single key 'score' and no premable or explanation.
    """

    user_prompt = f"""
        Question: {question} 
        Context: {doc_txt}  
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    response = json.loads(ollama.chat(model='llama3', messages=messages)['message']['content'])

    return docs, response

### Generate

def retrieve_answer(question = None):

    docs = retrieve_context(question)
    
    system_prompt = """
        You are an assistant for question-answering tasks. 
        Use the following pieces of retrieved context to answer the question. 
        If you don't know the answer, just say that you don't know. 
        Use three sentences maximum and keep the answer concise.
        Please answer the question in traditional Chinese.
    """

    user_prompt = f"""
        Question: {question} 
        Context: {docs}  
    """

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    return ollama.chat(model='llama3', messages=messages, stream=True)

def speech_to_text(file_path):
    recognizer = sr.Recognizer()

    with sr.AudioFile(file_path) as source:
        audio_data = recognizer.record(source)
    
    # Convert speech to text
    try:
        text = recognizer.recognize_google(audio_data, language='zh-tw')
        return text
    except sr.UnknownValueError:
        return "Speech not recognized"
    except sr.RequestError:
        return "Error: Could not request results from the speech recognition service"

@app.route('/')
def home():
    return render_template('chat.html')

@socketio.on('request')
def handle_request(data):
    message = data.get('message')

    docs, relevance = check_relevance(question = message)
    
    if relevance['score'] == 'irrelevant':
        emit('response', {'message': "The question is considered irrelevant.", 'references': "N/A"})
        return

    generation = ""
    for chunk in retrieve_answer(question = message):
        generation += chunk['message']['content']
        emit('response', {'message': generation, 'references': "N/A"})

    references = ""
    for doc in docs:
        doc_page, doc_source, doc_txt = doc.metadata["page"], doc.metadata["source"], doc.page_content
        references += f'{doc_source} 第{doc_page}頁:<br>\n'
        for line in doc.page_content.split('\n'):
            references += f"{line}<br>\n"
        references += "<br>\n"

    emit('response', {'message': generation, 'references': references})
    return

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'audio' not in request.files:
        return "No audio file provided", 400
    
    file = request.files['audio']
    if file.filename == '':
        return "No selected file", 400
    
    if file:
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(file_path)
        
        # Convert audio to the correct format if necessary
        if file.filename.endswith('.webm'):
            wav_path = file_path.replace('.webm', '.wav')
            subprocess.run(["ffmpeg", "-i", file_path, "-vn", "-ab", "128k", "-ar", "44100", "-y", wav_path])
            file_path = wav_path

        # Perform speech recognition
        text = speech_to_text(file_path)
        return text

    return redirect(url_for('index'))

@app.route('/files')
def get_files():
    try:
        # List all files in the directory (you can modify this part based on your use case)
        files = os.listdir(app.config['FILES_FOLDER'])
        return jsonify(files)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/download/<filename>')
def download_file(filename):
    try:
        # Check if the file exists in the user_files directory
        if os.path.exists(os.path.join(app.config['FILES_FOLDER'], filename)):
            return send_from_directory(app.config['FILES_FOLDER'], filename, as_attachment=True)
        else:
            abort(404)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)