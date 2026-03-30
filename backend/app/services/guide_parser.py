import csv
import io

from app.schemas.project import QuestionCreate


def parse_guide_csv(file_content: bytes) -> list[QuestionCreate]:
    """Parse a CSV file with interview guide questions.

    Expected columns:
        Section_index, Section_title, Question_index,
        Main_question, Interview_notes, Desired_learning

    Returns a list of QuestionCreate schemas ready to insert.
    """
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    questions: list[QuestionCreate] = []
    for row in reader:
        questions.append(
            QuestionCreate(
                section_index=int(row["Section_index"]),
                section_title=row.get("Section_title", ""),
                question_index=int(row["Question_index"]),
                main_question=row["Main_question"],
                interview_notes=row.get("Interview_notes", "") or "",
                desired_learning=row.get("Desired_learning", "") or "",
            )
        )

    return questions
