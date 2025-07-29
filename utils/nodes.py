from utils.react_state import State
from utils.vector_store_manager import CVEmbeddingManager
from langchain_core.messages import AIMessage, HumanMessage
from langchain_groq import ChatGroq
from dotenv import load_dotenv
from utils.config import THREAD_CONFIG

load_dotenv()

cv_manager = CVEmbeddingManager()
cv_manager.embed_and_store_cv("docs/CV_IA.pdf")
retriever = cv_manager.get_retriever(k=3)

llm = ChatGroq(model="llama-3.1-8b-instant")

def extract_cv_content(state: State):
    """Extrae el contenido completo del CV usando el retriever"""
    print("1. Extraer contenido del CV")
    docs = retriever.invoke("curriculum vitae experiencia educación habilidades")
    cv_text = "\n".join([doc.page_content for doc in docs])
    
    return {
        "cv_content": cv_text,
        "messages": state["messages"]
    }

def validate_cv_structure(state: State):
    """Valida si el CV tiene la estructura correcta e información importante"""
    print("2. Validar estructura del CV")
    cv_content = state["cv_content"]
    
    validation_prompt = f"""
    Analiza el siguiente CV y determina si tiene una estructura correcta y contiene información importante.
    Si el documento no es un CV o no tiene apariencia de CV, responde "INCOMPLETO".
    
    CV a analizar:
    {cv_content}
    
    Criterios a evaluar:
    1. Información personal (nombre, contacto)
    2. Experiencia laboral con fechas y descripciones
    3. Educación/formación académica
    4. Habilidades técnicas o competencias
    5. Estructura clara y coherente
    
    Responde únicamente con "VÁLIDO" si cumple con TODOS los criterios de forma obligatoria, 
    o "INCOMPLETO" si le falta cualquiera de los criterios mencionados. Tienes que ser muy estricto en la evaluación.
    """

    response = llm.invoke([HumanMessage(content=validation_prompt)], config=THREAD_CONFIG)
    is_valid = "VÁLIDO" in response.content.upper()
    
    return {
        "is_cv_valid": is_valid,
        "cv_content": cv_content,
        "messages": state["messages"]
    }

def provide_feedback(state: State):
    """Proporciona retroalimentación sobre qué mejorar en el CV"""
    print("4. Proporcionar retroalimentación sobre el CV")
    cv_content = state["cv_content"]
    
    feedback_prompt = f"""
    El siguiente CV tiene estructura incorrecta o le falta información importante:
    
    {cv_content}
    
    Proporciona retroalimentación específica sobre:
    1. Qué secciones faltan o están incompletas
    2. Qué información importante debería agregarse
    3. Cómo mejorar la estructura del documento
    4. Sugerencias para hacer el CV más atractivo para empleadores
    
    Sé específico y constructivo en tus recomendaciones.
    """
    
    response = llm.invoke([HumanMessage(content=feedback_prompt)], config=THREAD_CONFIG)
    feedback = response.content
    
    return {
        "feedback": feedback,
        "messages": state["messages"] + [AIMessage(content=f"Retroalimentación del CV:\n{feedback}")]
    }

def create_cv_summary(state: State):
    """Crea un resumen de lo más destacado del CV"""
    print("5. Crear resumen del CV")
    cv_content = state["cv_content"]
    
    summary_prompt = f"""
    Crea un resumen profesional destacando los puntos más importantes del siguiente CV:
    
    {cv_content}
    
    El resumen debe incluir:
    1. Perfil profesional breve
    2. Experiencia laboral más relevante (2-3 posiciones principales)
    3. Educación destacada
    4. Habilidades técnicas clave
    5. Logros o certificaciones importantes
    
    Presenta la información de manera clara y atractiva, como si fuera para un recruiter.
    """
    
    response = llm.invoke([HumanMessage(content=summary_prompt)], config=THREAD_CONFIG)
    summary = response.content
    
    return {
        "summary": summary,
        "messages": state["messages"] + [AIMessage(content=f"Resumen del CV:\n{summary}")]
    }

def route_after_validation(state: State):
    """Decide si ir al nodo de feedback o al de resumen"""
    print("3. Ruteo después de la validación del CV")
    if state["is_cv_valid"]:
        return "person_is_postuled_to_job"
    else:
        return "provide_feedback"
    
def person_is_postuled_to_job(state: State):
    """Simula que una persona se postula a un trabajo"""
    print("4. Verificar si la persona está postulando a un trabajo")
    decision = input("¿Estás postulando a un trabajo? (si/no): ").strip().lower()
    print("Decisión de postulación:", decision)
    print(decision == "si")
    return {
        "person_is_postuled_to_job": decision == "si",
        "messages": state["messages"] + [HumanMessage(content="Verificando si la persona está postulando a un trabajo...")]
    }

def route_after_postuling_to_job(state: State):
    """Simula que una persona se postula a un trabajo"""
    print("4. Verificar si la persona esta postulando a un trabajo")
    if state["person_is_postuled_to_job"]:
        print("La persona está postulando a un trabajo.")
        return "ask_info_about_job"
    else:
        print("La persona no está postulando a un trabajo.")
        return "create_summary"
    
def ask_info_about_job(state: State):
    """Solicita información sobre el trabajo al que se postula"""
    print("5. Solicitar información sobre el trabajo al que se postula")
    job_info = input("Proporciona información sobre el trabajo al que te postulas, puedes copiar y pegar desde la propia pagina web: ")
        
    print(f"Información del trabajo recibida: {job_info}")
    return {
        "job_info": job_info,
        "messages": state["messages"] + [HumanMessage(content=f"Información del trabajo recibida: {job_info[:100]}...")]
    }

def analyze_cv_job_compatibility(state: State):
    """Analiza la compatibilidad entre el CV y la oferta laboral"""
    print("6. Analizar compatibilidad CV-Trabajo")
    cv_content = state["cv_content"]
    job_info = state["job_info"]
    
    compatibility_prompt = f"""
    Analiza la compatibilidad entre este CV y la oferta laboral:
    
    CV DEL CANDIDATO:
    {cv_content}
    
    OFERTA LABORAL:
    {job_info}
    
    Proporciona un análisis que incluya:
    1. Porcentaje de compatibilidad (0-100%)
    2. Habilidades que coinciden
    3. Experiencia relevante encontrada
    4. Requisitos que NO cumple
    5. Sugerencias específicas para mejorar el CV para esta posición
    6. Recomendación final (POSTULAR/MEJORAR_CV/NO_COMPATIBLE)
    
    Sé específico y constructivo.
    """
    
    response = llm.invoke([HumanMessage(content=compatibility_prompt)], config=THREAD_CONFIG)
    analysis = response.content

    print("Análisis de compatibilidad:", analysis)
    
    return {
        "compatibility_analysis": analysis,
        "messages": state["messages"] + [AIMessage(content=f"Análisis de compatibilidad:\n{analysis}")]
    }
