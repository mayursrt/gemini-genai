from flask import Flask, request, jsonify
import os
import argparse
from tqdm import tqdm
import chromadb
import google.generativeai as genai
from chromadb import Documents, EmbeddingFunction, Embeddings
from typing import List
import PyPDF2
from bs4 import BeautifulSoup
import requests

app = Flask(__name__)

google_api_key = None
if "GOOGLE_API_KEY" not in os.environ:
    gapikey = input("Please enter your Google API Key: ")
    genai.configure(api_key=gapikey)
    google_api_key = gapikey
else:
    google_api_key = os.environ["GOOGLE_API_KEY"]


class GeminiEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        model = 'models/embedding-001'
        title = "Custom query"
        return genai.embed_content(model=model,
                                   content=input,
                                   task_type="retrieval_document",
                                   title=title)["embedding"]

# def clean_document(content: str) -> str:
#     cleaned_content = '\n'.join(' '.join(line.split()) for line in content.split('\n')).strip()
#     return cleaned_content


def clean_document(content: str) -> str:
    prompt = {
        "content": "Please clean the following document content. Ensure there is no data loss, remove extra whitespace, fix common typos, and ensure the text is properly formatted. Here is the content:\n\n"
                   f"{content}"
    }
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(prompt['content'])
    cleaned_content = response.text.strip()
    
    return cleaned_content

def load_data(tenant_id: str, persist_directory: str):
    raw_documents_directory = f"data/{tenant_id}/docs/raw"
    clean_documents_directory = f"data/{tenant_id}/docs/clean"
    os.makedirs(clean_documents_directory, exist_ok=True)

    documents = []
    metadatas = []
    files = os.listdir(raw_documents_directory)
    for filename in files:
        file_path = f"{raw_documents_directory}/{filename}"
        if filename.lower().endswith('.pdf'):
            content = ""
            with open(file_path, "rb") as file:
                reader = PyPDF2.PdfReader(file)
                for page in reader.pages:
                    content += page.extract_text() + "\n"
            clean_filename = filename.replace('.pdf', '.txt')
        else:
            with open(file_path, "r", encoding="utf8") as file:
                content = file.read()
            clean_filename = filename
        
        cleaned_content = clean_document(content)
        
        with open(f"{clean_documents_directory}/{clean_filename}", "w", encoding="utf8") as clean_file:
            clean_file.write(cleaned_content)
        
        for line_number, line in enumerate(cleaned_content.split('\n'), 1):
            if len(line.strip()) == 0:
                continue
            documents.append(line)
            metadatas.append({"filename": clean_filename, "line_number": line_number})

    client = chromadb.PersistentClient(path=persist_directory)


    collection_name = tenant_id

    collection = client.get_or_create_collection(
        name=collection_name, embedding_function=GeminiEmbeddingFunction()
    )

    count = collection.count()
    print(f"Collection already contains {count} documents")
    ids = [str(i) for i in range(count, count + len(documents))]

    for i in tqdm(
        range(0, len(documents), 100), desc="Adding documents", unit_scale=100
    ):
        collection.add(
            ids=ids[i : i + 100],
            documents=documents[i : i + 100],
            metadatas=metadatas[i : i + 100],  
        )

    new_count = collection.count()
    print(f"Added {new_count - count} documents")


def build_prompt(query: str, context: List[str]) -> str:
    base_prompt = {
        "content": "I am going to ask you a question, which I would like you to answer"
        " based only on the provided context, and not any other information."
        " If there is not enough information in the context to answer the question,"
        ' say "I am not sure", then try to make a guess.'
        " Break your answer up into nicely readable paragraphs.",
    }
    user_prompt = {
        "content": f" The question is '{query}'. Here is all the context you have:"
        f'{(" ").join(context)}',
    }

    system = f"{base_prompt['content']} {user_prompt['content']}"

    return system

def get_gemini_response(query: str, context: List[str]) -> str:
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(build_prompt(query, context))
    return response.text


@app.route('/load_data', methods=['POST'])
def api_load_data():
    tenant_id = request.json.get('tenantid')
    persist_directory = request.json.get('persist_directory','db')
    load_data(tenant_id, persist_directory)
    return jsonify({"message": "Data loaded successfully"}), 200

@app.route('/get_answer', methods=['POST'])
def api_get_answer():
    tenant_id = request.json.get('tenantid')
    persist_directory = request.json.get('persist_directory','db')
    query = request.json.get('query')
    
    client = chromadb.PersistentClient(path=persist_directory)
    collection = client.get_collection(
        name=tenant_id, embedding_function=GeminiEmbeddingFunction()
    )

    results = collection.query(
        query_texts=[query], n_results=5, include=["documents", "metadatas"]
    )

    response = get_gemini_response(query, results["documents"][0])
    sources = "\n".join(
        [
            f"{result['filename']}: line {result['line_number']}"
            for result in results["metadatas"][0]  
        ]
    )

    return jsonify({"response": response, "sources": sources}), 200



if __name__ == '__main__':
    app.run(debug=True)
