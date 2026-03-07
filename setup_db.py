"""
setup_db.py — Ingest Network SOPs & Past Incidents into ChromaDB.

Usage:
    python setup_db.py

Requires GOOGLE_API_KEY environment variable for embeddings.
"""

import os
from dotenv import load_dotenv

load_dotenv()

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter

# --- Configuration ---
SOP_FILE = os.path.join("data", "sops.md")
CHROMA_DIR = "./chroma_db"
COLLECTION_NAME = "network_sops"


def main():
    # 1. Read the SOP markdown file
    if not os.path.exists(SOP_FILE):
        print(f"❌ Error: {SOP_FILE} not found. Place your SOP file in data/sops.md")
        return

    with open(SOP_FILE, "r", encoding="utf-8") as f:
        raw_text = f.read()

    print(f"📄 Loaded {len(raw_text)} characters from {SOP_FILE}")

    # 2. Split by ## headings (each SOP/incident becomes a chunk)
    splitter = RecursiveCharacterTextSplitter(
        separators=["\n## ", "\n---\n"],
        chunk_size=1500,
        chunk_overlap=200,
        keep_separator=True,
    )
    chunks = splitter.split_text(raw_text)
    print(f"✂️  Split into {len(chunks)} chunks")

    # 3. Setup Google Generative AI Embeddings
    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=os.getenv("GOOGLE_API_KEY"),
    )

    # 4. Create/overwrite the ChromaDB collection
    vectorstore = Chroma.from_texts(
        texts=chunks,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=CHROMA_DIR,
    )

    print(f"✅ Successfully ingested {len(chunks)} chunks into ChromaDB")
    print(f"   Collection: {COLLECTION_NAME}")
    print(f"   Directory:  {CHROMA_DIR}")

    # 5. Quick verification — test a query
    results = vectorstore.similarity_search("high latency on Core-Router-Mumbai", k=2)
    print(f"\n🔍 Test query: 'high latency on Core-Router-Mumbai'")
    for i, doc in enumerate(results):
        preview = doc.page_content[:120].replace("\n", " ")
        print(f"   Result {i+1}: {preview}...")


if __name__ == "__main__":
    main()
