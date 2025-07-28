import os
from langchain_community.vectorstores import FAISS
from langchain_community.document_loaders import TextLoader, PyPDFLoader, Docx2txtLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceBgeEmbeddings


class CVEmbeddingManager:
    def __init__(self, faiss_path: str = "cv_faiss_index"):
        self.faiss_path = faiss_path
        self.embeddings = HuggingFaceBgeEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            model_kwargs={'device': 'cuda'},
            encode_kwargs={'normalize_embeddings': True}
        )

    def load_cv(self, file_path: str):
        """Carga un CV desde archivo local, soportando .txt, .pdf y .docx"""
        ext = os.path.splitext(file_path)[1].lower()

        if ext == ".txt":
            loader = TextLoader(file_path)
        elif ext == ".pdf":
            loader = PyPDFLoader(file_path)
        elif ext == ".docx":
            loader = Docx2txtLoader(file_path)
        else:
            raise ValueError(f"Formato de archivo no soportado: {ext}")

        print(f"Cargando CV desde {file_path}...")
        docs = loader.load()
        return docs

    def embed_and_store_cv(self, file_path: str):
        """Genera embeddings del CV y los guarda en un índice FAISS local"""
        docs = self.load_cv(file_path)

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200
        )
        split_docs = text_splitter.split_documents(docs)

        vectors = FAISS.from_documents(split_docs, self.embeddings)
        vectors.save_local(self.faiss_path)
        print("Embeddings generados y guardados exitosamente en FAISS.")

        return vectors

    def get_retriever(self, k=5):
        """Devuelve un retriever configurado para el CV embebido"""
        if not os.path.exists(self.faiss_path):
            raise FileNotFoundError("No existe índice FAISS. Ejecuta primero `embed_and_store_cv()`.")
        
        vectors = FAISS.load_local(
            folder_path=self.faiss_path,
            embeddings=self.embeddings,
            allow_dangerous_deserialization=True
        )
        retriever = vectors.as_retriever(search_kwargs={"k": k})
        return retriever
