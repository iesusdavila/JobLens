from app.domain.cv_models import CvChange, TailoredCv, TailoredCvDraft, TailoredExperience
from app.domain.job_models import ParsedJob
from app.domain.profile_models import CandidateProfile, EducationEntry, ExperienceEntry

CV_TEXT = """Jane Doe
jane@example.com | Madrid, Spain

SUMMARY
Backend engineer with 6 years of experience building Python services.

EXPERIENCE
Senior Backend Engineer | Acme Corp | 2021 - Present
- Built FastAPI services handling 2M requests per day
- Led migration from MySQL to PostgreSQL
- Mentored 3 junior engineers

Backend Engineer | Beta Labs | 2018 - 2021
- Developed Django REST APIs for a logistics platform
- Wrote CI pipelines with GitHub Actions

EDUCATION
BSc Computer Science | Universidad Politecnica de Madrid | 2014 - 2018

SKILLS
Python, FastAPI, Django, PostgreSQL, Docker, GitHub Actions
"""

JOB_TEXT = """Senior Python Engineer - Gamma Analytics (Remote, EU)
We are looking for a Senior Python Engineer to build our data platform microservices.
Requirements:
- 5+ years of Python experience
- Strong FastAPI knowledge
- PostgreSQL in production
- Kubernetes in production
Nice to have:
- AWS
- CI/CD automation
Responsibilities: design microservices, own CI/CD, mentor engineers.
"""

def parsed_job() -> ParsedJob:
    return ParsedJob(
        title="Senior Python Engineer",
        company="Gamma Analytics",
        seniority_level="senior",
        min_years_experience=5,
        must_have_requirements=["5+ years of Python experience", "Strong FastAPI knowledge", "PostgreSQL in production", "Kubernetes in production"],
        nice_to_have_requirements=["AWS", "CI/CD automation"],
        responsibilities=["Design microservices", "Own CI/CD", "Mentor engineers"],
        keywords=["Python", "FastAPI", "PostgreSQL", "Kubernetes", "microservices", "CI/CD"],
        domain="Data analytics",
        location="Remote, EU",
        modality="remote",
    )

def candidate_profile() -> CandidateProfile:
    return CandidateProfile(
        full_name="Jane Doe",
        contact_line="jane@example.com | Madrid, Spain",
        headline="Backend engineer",
        summary="Backend engineer with 6 years of experience building Python services.",
        total_years_experience=6,
        skills=["Python", "FastAPI", "Django", "PostgreSQL", "Docker", "GitHub Actions"],
        experiences=[
            ExperienceEntry(title="Senior Backend Engineer", employer="Acme Corp", start_date="2021", end_date="Present", highlights=["Built FastAPI services handling 2M requests per day", "Led migration from MySQL to PostgreSQL", "Mentored 3 junior engineers"]),
            ExperienceEntry(title="Backend Engineer", employer="Beta Labs", start_date="2018", end_date="2021", highlights=["Developed Django REST APIs for a logistics platform", "Wrote CI pipelines with GitHub Actions"]),
        ],
        education=[EducationEntry(degree="BSc Computer Science", institution="Universidad Politecnica de Madrid", start_date="2014", end_date="2018")],
    )

def tailored_draft(fabricate: bool = False) -> TailoredCvDraft:
    first_bullets = ["Built FastAPI microservices in Python handling 2M requests per day", "Led migration from MySQL to PostgreSQL", "Mentored 3 junior engineers"]
    if fabricate:
        first_bullets.append("FABRICATED: Ran Kubernetes clusters in production")
    cv = TailoredCv(
        language="en",
        full_name="Someone Else",
        contact_line="jane@example.com | Madrid, Spain",
        headline="Senior Python backend engineer",
        summary="Python backend engineer with 6 years building FastAPI microservices and PostgreSQL systems.",
        skills=["Python", "FastAPI", "PostgreSQL", "Django", "Docker", "GitHub Actions"],
        experiences=[
            TailoredExperience(title="Lead Backend Engineer", employer="Acme Corp", start_date="2021", end_date="Present", bullets=first_bullets),
            TailoredExperience(title="Backend Engineer", employer="Beta Labs", start_date="2018", end_date="2021", bullets=["Built CI/CD pipelines with GitHub Actions", "Developed Django REST APIs for a logistics platform"]),
            TailoredExperience(title="Staff Engineer", employer="Invented Inc", start_date="2010", end_date="2012", bullets=["Did things"]),
        ],
        education=[EducationEntry(degree="BSc Computer Science", institution="Universidad Politecnica de Madrid", start_date="2014", end_date="2018")],
        certifications=["AWS Solutions Architect"],
    )
    changes = [CvChange(section="experience", original="Built FastAPI services handling 2M requests per day", tailored="Built FastAPI microservices in Python handling 2M requests per day", reason="Mirrors the job's 'microservices' term.")]
    return TailoredCvDraft(cv=cv, changes=changes)
