from new_cv.react_state import ImproveCVState
from utils.vector_store_manager import CVEmbeddingManager
from langchain_core.messages import HumanMessage
from langchain_groq import ChatGroq
from utils.config import THREAD_CONFIG
import os
import json

llm = ChatGroq(model="llama-3.1-8b-instant")

def extract_cv_sections(state: ImproveCVState):
    """Extrae las secciones del CV usando el índice FAISS existente"""
    print("1. Extrayendo secciones del CV...")
    
    faiss_path = "cv_faiss_index"
    if os.path.exists(faiss_path):
        print("Usando índice FAISS existente...")
        cv_manager = CVEmbeddingManager(faiss_path)
        retriever = cv_manager.get_retriever(k=10)
        
        sections = {}
        section_queries = {
            "personal_info": "información personal nombre contacto teléfono email",
            "experience": "experiencia laboral trabajo empresa puesto responsabilidades",
            "education": "educación formación académica universidad estudios título",
            "skills": "habilidades competencias técnicas lenguajes programación",
            "achievements": "logros certificaciones premios reconocimientos"
        }
        
        for section, query in section_queries.items():
            docs = retriever.invoke(query)
            sections[section] = "\n".join([doc.page_content for doc in docs[:3]])
    else:
        print("No existe índice FAISS, usando contenido original...")
        sections = {"raw_content": state["cv_content"]}
    
    return {
        "cv_sections": sections,
        "cv_content": state["cv_content"],
        "feedback": state["feedback"]
    }

def improve_cv_structure(state: ImproveCVState):
    """Mejora la estructura del CV basado en el feedback"""
    print("2. Mejorando estructura del CV...")
    
    cv_sections = state["cv_sections"]
    feedback = state["feedback"]
    
    improvement_prompt = f"""
    Basándote en el siguiente feedback y las secciones del CV, crea una versión mejorada:

    FEEDBACK RECIBIDO:
    {feedback}

    SECCIONES DEL CV:
    {json.dumps(cv_sections, indent=2, ensure_ascii=False)}

    INSTRUCCIONES:
    1. Corrige todas las deficiencias mencionadas en el feedback
    2. Mejora la estructura siguiendo estas secciones estándar:
       - Información Personal (nombre, contacto, perfil profesional)
       - Experiencia Profesional (con fechas, empresa, logros específicos)
       - Educación (títulos, instituciones, fechas)
       - Habilidades Técnicas (organizadas por categorías)
       - Certificaciones/Logros (si aplica)
    3. Usa un formato profesional y consistente
    4. Agrega información que pueda estar faltando basándote en el contexto
    5. Mejora la redacción para hacerla más impactante

    Responde ÚNICAMENTE con el CV mejorado en formato texto plano, bien estructurado.
    """
    
    response = llm.invoke([HumanMessage(content=improvement_prompt)], config=THREAD_CONFIG)
    improved_content = response.content
    
    return {
        "improved_cv": improved_content,
        "cv_sections": cv_sections,
        "feedback": feedback
    }

def format_improved_cv(state: ImproveCVState):
    """Formatea el CV mejorado para mejor presentación"""
    print("3. Formateando CV mejorado...")
    
    improved_cv = state["improved_cv"]
    
    formatting_prompt = f"""
    Toma el siguiente CV mejorado y dale un formato profesional final:

    {improved_cv}

    INSTRUCCIONES DE FORMATO:
    1. Asegúrate de que tenga títulos claros y bien definidos
    2. Usa viñetas (•) para listas
    3. Organiza la información de manera lógica y fácil de leer
    4. Asegúrate de que las fechas estén en formato consistente
    5. Mantén un estilo profesional y limpio
    6. Agrega espaciado apropiado entre secciones

    Responde ÚNICAMENTE con el CV final formateado.
    """
    
    response = llm.invoke([HumanMessage(content=formatting_prompt)], config=THREAD_CONFIG)
    final_cv = response.content
    
    return {
        "improved_cv": final_cv
    }