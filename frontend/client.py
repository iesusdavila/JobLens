import streamlit as st
import requests
import json
from typing import Optional
import io

# Configuración de la página
st.set_page_config(
    page_title="JobLens - Análisis de CV",
    page_icon="📄",
    layout="wide"
)

API_URL = "http://localhost:8000/joblens/invoke"

def send_request(person_is_postuled_to_job: bool, job_info: Optional[str] = None) -> dict:
    """
    Envía una petición a la API de JobLens
    """
    payload = {
        "input": {
            "person_is_postuled_to_job": person_is_postuled_to_job,
            "job_info": job_info if job_info else ""
        },
        "config": {},
        "kwargs": {
            "additionalProp1": {}
        }
    }
    
    try:
        response = requests.post(API_URL, json=payload, timeout=30)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        st.error(f"Error al conectar con la API: {str(e)}")
        return {}

def main():
    st.title("📄 JobLens - Análisis de CV")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("📁 Configuración")
        
        # 1. Selector de CV
        st.subheader("1. Seleccionar CV")
        uploaded_file = st.file_uploader(
            "Selecciona tu CV",
            type=['pdf', 'doc', 'docx', 'txt'],
            help="Formatos soportados: PDF, DOC, DOCX, TXT"
        )
        
        if uploaded_file:
            st.success(f"✅ Archivo cargado: {uploaded_file.name}")
            file_details = {
                "Nombre": uploaded_file.name,
                "Tipo": uploaded_file.type,
                "Tamaño": f"{uploaded_file.size} bytes"
            }
            st.json(file_details)
        
        st.markdown("---")
        
        st.subheader("2. Estado de búsqueda laboral")
        is_looking_for_job = st.toggle(
            "¿Estás buscando trabajo actualmente?",
            value=False,
            help="Activa esta opción si estás buscando trabajo actualmente"
        )
        
        job_description = ""
        if is_looking_for_job:
            st.subheader("3. Descripción del trabajo")
            job_description = st.text_area(
                "Descripción completa del trabajo",
                height=200,
                placeholder="Pega aquí toda la descripción del trabajo al que te estás postulando...",
                help="Incluye todos los detalles relevantes: responsabilidades, requisitos, tecnologías, etc."
            )
        else:
            st.info("Activa 'búsqueda de trabajo' para ingresar la descripción del puesto")
        
        st.markdown("---")
        
        analyze_button = st.button(
            "Analizar CV",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_file
        )
    
    with col2:
        st.header("Resultado del Análisis")
        
        if analyze_button and uploaded_file:
            with st.spinner("Analizando tu CV..."):
                response = send_request(is_looking_for_job, job_description)
                
                if response:
                    st.success("Análisis completado")
                    
                    if 'output' in response:
                        st.subheader("Análisis del CV")
                        
                        st.write(response)
                    else:
                        st.warning("No se recibió una respuesta válida del servidor")
                        st.json(response)
                else:
                    st.error("No se pudo obtener respuesta del servidor")
        
        elif not uploaded_file:
            st.info("📤 Por favor, carga un CV para comenzar el análisis")
        
if __name__ == "__main__":
    main()