import os
import argparse
from tqdm import tqdm
import chromadb
import google.generativeai as genai
from chromadb import Documents, EmbeddingFunction, Embeddings

class GeminiEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        model = 'models/embedding-001'
        title = "Custom query"
        return genai.embed_content(model=model,
                                   content=input,
                                   task_type="retrieval_document",
                                   title=title)["embedding"]

def clean_document(content: str) -> str:
    """
    Clean the entire document content while ensuring no data loss.
    This could include removing extra whitespace, fixing common typos, etc.
    """
    # Example: Strip leading/trailing whitespace from each line and replace multiple spaces with a single space
    cleaned_content = '\n'.join(' '.join(line.split()) for line in content.split('\n')).strip()
    return cleaned_content

def main(
    tenant_id: str = "fcd15f72-4bfa-449b-8e7e-dc4948c109db",
    persist_directory: str = ".",
) -> None:
    raw_documents_directory = f"data/{tenant_id}/raw"
    clean_documents_directory = f"data/{tenant_id}/clean"
    os.makedirs(clean_documents_directory, exist_ok=True)

    # Read and clean all files in the raw documents directory
    documents = []
    metadatas = []
    files = os.listdir(raw_documents_directory)
    for filename in files:
        with open(f"{raw_documents_directory}/{filename}", "r", encoding="utf8") as file:
            content = file.read()
            cleaned_content = clean_document(content)
            
            with open(f"{clean_documents_directory}/{filename}", "w", encoding="utf8") as clean_file:
                clean_file.write(cleaned_content)
            
            for line_number, line in enumerate(cleaned_content.split('\n'), 1):
                # Skip empty lines
                if len(line.strip()) == 0:
                    continue
                documents.append(line)
                metadatas.append({"filename": filename, "line_number": line_number})

    # Instantiate a persistent Chroma client in the persist directory.
    # Learn more at docs.trychroma.com
    client = chromadb.PersistentClient(path=persist_directory)

    google_api_key = None
    if "GOOGLE_API_KEY" not in os.environ:
        gapikey = input("Please enter your Google API Key: ")
        genai.configure(api_key=gapikey)
        google_api_key = gapikey
    else:
        google_api_key = os.environ["GOOGLE_API_KEY"]

    # Use tenant_id as the collection name
    collection_name = tenant_id

    # If the collection already exists, we just return it. This allows us to add more
    # data to an existing collection.
    collection = client.get_or_create_collection(
        name=collection_name, embedding_function=GeminiEmbeddingFunction()
    )

    # Create ids from the current count
    count = collection.count()
    print(f"Collection already contains {count} documents")
    ids = [str(i) for i in range(count, count + len(documents))]

    # Load the documents in batches of 100
    for i in tqdm(
        range(0, len(documents), 100), desc="Adding documents", unit_scale=100
    ):
        collection.add(
            ids=ids[i : i + 100],
            documents=documents[i : i + 100],
            metadatas=metadatas[i : i + 100],  # type: ignore
        )

    new_count = collection.count()
    print(f"Added {new_count - count} documents")

if __name__ == "__main__":
    # Read the tenant_id and persist directory
    parser = argparse.ArgumentParser(
        description="Load documents from a directory into a Chroma collection"
    )

    # Add arguments
    parser.add_argument(
        "--tenant_id",
        type=str,
        default="fcd15f72-4bfa-449b-8e7e-dc4948c109db",
        # required=True,
        help="The tenant ID used to identify the document directories and collection name",
    )
    parser.add_argument(
        "--persist_directory",
        type=str,
        default="chroma_storage",
        help="The directory where you want to store the Chroma collection",
    )

    # Parse arguments
    args = parser.parse_args()

    main(
        tenant_id=args.tenant_id,
        persist_directory=args.persist_directory,
    )
