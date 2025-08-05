import streamlit as st
import requests
import tempfile
from typing import Optional

# Configuración de la página
st.config.set_option('server.port', 8501)

st.set_page_config(
    page_title="JobLens - Analysis CV",
    page_icon="",
    layout="wide"
)

API_URL = "http://localhost:8000/joblens/invoke"
API_URL_IMPROVE_CV = "http://localhost:8000/joblens/improve-cv/invoke"

def send_request(cv_file_path: str, person_is_postuled_to_job: bool, job_info: Optional[str] = None) -> dict:
    payload = {
        "input": {
            "person_is_postuled_to_job": person_is_postuled_to_job,
            "job_info": job_info if job_info else "",
            "cv_file_path": cv_file_path
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

def send_improve_cv_request(cv_content: str, feedback: str, cv_file_path: str) -> dict:
    improve_payload = {
        "input": {
            "cv_content": cv_content,
            "feedback": feedback,
            "cv_file_path": cv_file_path
        },
        "config": {},
        "kwargs": {}
    }
    
    improve_response = requests.post(
        API_URL_IMPROVE_CV,
        json=improve_payload, 
        timeout=60
    )
    
    if improve_response.status_code == 200:
        improved_data = improve_response.json()
        st.success("Improved CV generated successfully!")
        
        with st.expander("Improved CV", expanded=True):
            st.markdown(improved_data['output'].get('improved_cv', 'No improved CV generated.'))
        
        if improved_data['output'].get('improved_cv'):
            st.download_button(
                label="Download Improved CV",
                data=improved_data['output']['improved_cv'],
                file_name="improved_cv.txt",
                mime="text/plain"
            )
    else:
        st.error("Failed to generate improved CV.")

def main():
    st.title("JobLens - Analysis CV")
    st.markdown("---")
    
    # Inicializar session state
    if 'analysis_results' not in st.session_state:
        st.session_state.analysis_results = None
    if 'show_generate_cv' not in st.session_state:
        st.session_state.show_generate_cv = False
    
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.header("Configuration")
        
        st.subheader("1. Upload Your CV")
        uploaded_file = st.file_uploader(
            "Selecciona tu CV",
            type=['pdf', 'doc', 'docx', 'txt'],
            help="Formats supported: PDF, DOC, DOCX, TXT"
        )

        file_path = ""
        
        if uploaded_file:
            st.success(f"File loaded: {uploaded_file.name}")

            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{uploaded_file.name}") as tmp_file:
                tmp_file.write(uploaded_file.getvalue())
                file_path = tmp_file.name
            
            file_details = {
                "Name": uploaded_file.name,
                "Type": uploaded_file.type,
                "Size": f"{uploaded_file.size} bytes",
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
                response = send_request(file_path, is_looking_for_job, job_description)
                
                if response:
                    st.session_state.analysis_results = response
                    st.session_state.show_generate_cv = False
        
        # Mostrar resultados si existen en session_state
        if st.session_state.analysis_results:
            response = st.session_state.analysis_results
            st.success("Analysis completed successfully!")
            
            if 'output' in response:   
                if isinstance(response['output']["is_cv_valid"], bool):
                    st.subheader(f"CV Validity: {'Valid' if response['output']['is_cv_valid'] else 'Invalid'}")

                    if not response['output']['is_cv_valid']:
                        st.subheader("Feedback")
                        st.write(response['output'].get('feedback', 'No feedback provided.'))

                        generate_new_cv = st.button(
                            "Generate New CV",
                            type="secondary",
                            use_container_width=True,
                            key="generate_cv_btn"
                        )

                        if generate_new_cv:
                            st.session_state.show_generate_cv = True
                            
                        if st.session_state.show_generate_cv:
                            st.success("Generating a new CV based on the feedback provided.")

                            with st.spinner("Generating improved CV..."):
                                cv_content = response['output'].get('cv_content', '')
                                feedback = response['output'].get('feedback', 'No feedback provided.')
                                file_path = response['output'].get('cv_file_path', '')

                                send_improve_cv_request(cv_content, feedback, file_path)

                    else:
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
        
        elif not uploaded_file:
            st.info("Please upload your CV to start the analysis.")

if __name__ == "__main__":
    main()