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
        st.error(f"Error connecting to the API: {e}")
        return {}

def main():
    st.title("JobLens - Analysis CV")
    st.markdown("---")
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("Configuration")
        
        st.subheader("1. Seleccionar CV")
        uploaded_file = st.file_uploader(
            "Selecciona tu CV",
            type=['pdf', 'doc', 'docx', 'txt'],
            help="Formats supported: PDF, DOC, DOCX, TXT"
        )
        
        if uploaded_file:
            st.success(f"File loaded: {uploaded_file.name}")
            file_details = {
                "Name": uploaded_file.name,
                "Type": uploaded_file.type,
                "Size": f"{uploaded_file.size} bytes"
            }
            st.json(file_details)
        
        st.markdown("---")
        
        st.subheader("2. State of Job Search")
        is_looking_for_job = st.toggle(
            "Are you currently looking for a job?",
            value=False,
            help="Activate this if you want to analyze your CV against a specific job description",
        )
        
        job_description = ""
        if is_looking_for_job:
            st.subheader("3. Job Description")
            job_description = st.text_area(
                "Description of the Job",
                height=200,
                placeholder="Paste the job description here...",
                help="Include details such as job title, responsibilities, and requirements."
            )
        else:
            st.info("Activate the toggle to analyze your CV against a specific job description.")
        
        st.markdown("---")
        
        analyze_button = st.button(
            "Analyze CV",
            type="primary",
            use_container_width=True,
            disabled=not uploaded_file
        )
    
    with col2:
        st.header("Analysis Results")
        
        if analyze_button and uploaded_file:
            with st.spinner("Analyzing your CV..."):
                response = send_request(is_looking_for_job, job_description)
                
                if response:
                    st.success("Analysis completed successfully!")
                    
                    if 'output' in response:   

                        if isinstance(response['output']["is_cv_valid"], bool):
                            st.subheader(f"CV Validity: {'Valid' if response['output']['is_cv_valid'] else 'Invalid'}")

                            if not response['output']['is_cv_valid']:
                                st.subheader("Feedback")
                                st.write(response['output'].get('feedback', 'No feedback provided.'))

                        if isinstance(response["output"]["person_is_postuled_to_job"], bool):

                            if response["output"]["person_is_postuled_to_job"]:
                                st.subheader("Compatibility Analysis")
                                st.write(response['output'].get('compatibility_analysis', 'No compatibility analysis provided.'))
                            else:
                                st.subheader("Summary for your CV")
                                st.write(response['output'].get('summary', 'No summary provided.'))

                        with st.expander("CV Content", expanded=True):
                            st.text_area("CV Content", value=response['output'].get('cv_content', 'No CV content provided.'), height=300)
                            
                    else:
                        st.warning("No output found in the response.")
                        st.json(response)
                else:
                    st.error("Failed to get a valid response from the API.")
        
        elif not uploaded_file:
            st.info("Please upload your CV to start the analysis.")
        
if __name__ == "__main__":
    main()