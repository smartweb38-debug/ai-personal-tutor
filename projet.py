
import json
import re
from io import BytesIO

import fitz
import pytesseract
import streamlit as st
from PIL import Image
from google import genai


# ---------------------------
# إعداد الصفحة
# ---------------------------
st.set_page_config(
    page_title="المدرس الشخصي الذكي",
    page_icon="🎓",
    layout="centered",
)

st.title("🎓 المدرس الشخصي الذكي")
st.write(
    "ارفع درسك، احصل على ملخص باللغة العربية، "
    "واختبر معلوماتك بالذكاء الاصطناعي."
)


# ---------------------------
# مفتاح Gemini السري
# ---------------------------
try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except Exception:
    st.error(
        "تعذّر إعداد Gemini API. "
        "تحقّق من إعدادات Secrets في Streamlit."
    )
    st.stop()


MODEL = "gemini-3.5-flash-lite"


# ---------------------------
# استخراج النص من PDF مع OCR
# ---------------------------
def extract_pdf_text(pdf_bytes):
    document = fitz.open(
        stream=pdf_bytes,
        filetype="pdf",
    )

    pages_text = []

    for page_number, page in enumerate(document, start=1):
        page_text = page.get_text().strip()

        # استخدم OCR إذا كانت الصفحة مصوّرة
        if len(page_text) < 30:
            pix = page.get_pixmap(
                matrix=fitz.Matrix(2, 2),
                alpha=False,
            )

            image = Image.open(
                BytesIO(pix.tobytes("png"))
            )

            page_text = pytesseract.image_to_string(
                image,
                lang="ara+eng",
            ).strip()

        pages_text.append(page_text)

    document.close()

    return "\n\n".join(pages_text).strip()


# ---------------------------
# تنظيف JSON القادم من Gemini
# ---------------------------
def parse_quiz_json(raw_text):
    raw = (raw_text or "").strip()

    # إزالة علامات Markdown إذا أضافها النموذج
    raw = re.sub(
        r"^\s*```(?:json)?\s*",
        "",
        raw,
        flags=re.IGNORECASE,
    )
    raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # استخراج كائن JSON من الرد إذا وُجد نص زائد حوله
        start = raw.find("{")
        end = raw.rfind("}")

        if start == -1 or end <= start:
            raise ValueError(
                "لم يُرجع النموذج JSON صالحًا. حاول إنشاء الاختبار مجددًا."
            )

        candidate = raw[start:end + 1]

        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            # إصلاح الشرطة المائلة غير الصالحة داخل النصوص فقط
            fixed = re.sub(
                r'\\(?!["\\/bfnrtu])',
                r'\\\\',
                candidate,
            )
            data = json.loads(fixed)

    if not isinstance(data, dict):
        raise ValueError("تنسيق الاختبار غير صحيح.")

    questions = data.get("questions")

    if not isinstance(questions, list) or len(questions) != 10:
        raise ValueError("يجب أن يحتوي الاختبار على 10 أسئلة.")

    for q in questions:
        if not isinstance(q, dict):
            raise ValueError("تنسيق أحد الأسئلة غير صحيح.")

        if not isinstance(q.get("question"), str):
            raise ValueError("أحد الأسئلة لا يحتوي على نص صحيح.")

        options = q.get("options")
        if not isinstance(options, list) or len(options) != 4:
            raise ValueError("يجب أن يحتوي كل سؤال على أربعة خيارات.")

        if not all(isinstance(option, str) for option in options):
            raise ValueError("أحد خيارات الإجابة غير صالح.")

        correct = q.get("correct_answer")
        if type(correct) is not int or correct not in range(4):
            raise ValueError("رقم الإجابة الصحيحة غير صالح.")

        if not isinstance(q.get("explanation"), str):
            q["explanation"] = "لا يتوفر شرح لهذا السؤال."

    return questions


# ---------------------------
# رفع الدرس
# ---------------------------
uploaded_file = st.file_uploader(
    "📄 اختر ملف الدرس بصيغة PDF",
    type=["pdf"],
)

if uploaded_file and st.button(
    "📚 تحليل الدرس",
    type="primary",
):
    try:
        with st.spinner(
            "جارٍ استخراج النص من صفحات الدرس..."
        ):
            lesson_text = extract_pdf_text(
                uploaded_file.getvalue()
            )

        if len(lesson_text) < 100:
            st.error(
                "لم نستطع استخراج نص كافٍ من الملف. "
                "تحقّق من وضوح الصفحات أو من لغة المستند."
            )
            st.stop()

        with st.spinner("🤖 جارٍ تلخيص الدرس..."):
            summary_response = client.models.generate_content(
                model=MODEL,
                contents=(
                    "أنت مدرس خبير. لخّص الدرس التالي باللغة العربية "
                    "بشكل منظم وواضح، مع العناوين والمفاهيم الأساسية. "
                    "لا تضف معلومات غير موجودة في الدرس.\n\n"
                    + lesson_text[:18000]
                ),
            )

        summary = summary_response.text

        if not summary:
            st.error("لم يتم إنشاء الملخص. حاول مرة أخرى.")
            st.stop()

        st.session_state["summary"] = summary
        st.session_state["lesson_text"] = lesson_text
        st.session_state["quiz"] = None

        st.success("✅ تم استخراج الدرس وإنشاء الملخص!")

    except Exception as e:
        st.error(f"حدث خطأ أثناء تحليل الدرس: {e}")


# ---------------------------
# عرض الملخص وإنشاء الاختبار
# ---------------------------
if st.session_state.get("summary"):
    st.divider()
    st.subheader("📝 ملخص الدرس")
    st.markdown(st.session_state["summary"])

    if st.button(
        "🧠 إنشاء اختبار من 10 أسئلة",
        type="primary",
    ):
        prompt = f"""
أنت مدرس جامعي خبير.

أنشئ 10 أسئلة اختيار من متعدد باللغة العربية اعتمادًا
على الدرس التالي فقط.

الشروط:
- أربعة خيارات لكل سؤال.
- إجابة صحيحة واحدة فقط.
- أسئلة متنوعة حول المفاهيم والتعريفات والتطبيقات.
- شرح مختصر لكل إجابة صحيحة.
- أعد JSON صالحًا فقط دون Markdown أو نص إضافي.
- لا تستخدم شرطات مائلة عكسية غير ضرورية داخل النصوص.

استخدم هذا الشكل:
{{
  "questions": [
    {{
      "question": "نص السؤال",
      "options": [
        "الخيار الأول",
        "الخيار الثاني",
        "الخيار الثالث",
        "الخيار الرابع"
      ],
      "correct_answer": 0,
      "explanation": "شرح الإجابة"
    }}
  ]
}}

correct_answer هو رقم الخيار الصحيح بدءًا من الصفر.

الدرس:
{st.session_state["summary"][:9000]}
"""

        try:
            with st.spinner(
                "🤖 جارٍ إعداد الأسئلة وتصحيح تنسيقها..."
            ):
                quiz_response = client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                )

            questions = parse_quiz_json(
                quiz_response.text
            )

            st.session_state["quiz"] = questions
            st.session_state["quiz_id"] = (
                st.session_state.get("quiz_id", 0) + 1
            )

            st.success("✅ تم إنشاء الأسئلة بنجاح!")

        except Exception as e:
            st.error(
                f"تعذّر إنشاء الاختبار: {e}"
            )


# ---------------------------
# الاختبار والتصحيح
# ---------------------------
if st.session_state.get("quiz"):
    questions = st.session_state["quiz"]
    quiz_id = st.session_state.get("quiz_id", 1)

    st.divider()
    st.subheader("🧠 اختبر معلوماتك")

    with st.form(f"quiz_form_{quiz_id}"):
        answers = {}

        for i, q in enumerate(questions):
            st.markdown(
                f"**السؤال {i + 1}: {q['question']}**"
            )

            answers[i] = st.radio(
                "اختر إجابتك:",
                options=range(4),
                format_func=lambda x, opts=q["options"]: opts[x],
                index=None,
                key=f"answer_{quiz_id}_{i}",
            )

        submitted = st.form_submit_button(
            "✅ تصحيح الاختبار",
            type="primary",
        )

    if submitted:
        if any(answer is None for answer in answers.values()):
            st.warning("أجب عن جميع الأسئلة أولًا.")
        else:
            score = 0

            st.subheader("📊 نتيجة الاختبار")

            for i, q in enumerate(questions):
                selected = answers[i]
                correct = q["correct_answer"]

                if selected == correct:
                    score += 1
                    st.success(
                        f"السؤال {i + 1}: إجابة صحيحة!"
                    )
                else:
                    st.error(
                        f"السؤال {i + 1}: "
                        f"الإجابة الصحيحة هي: "
                        f"{q['options'][correct]}"
                    )

                st.caption(q["explanation"])

            percentage = round(
                score / len(questions) * 100
            )

            st.subheader(
                f"🎯 نتيجتك: {score} من {len(questions)}"
            )
            st.progress(percentage / 100)
            st.write(f"النسبة المئوية: {percentage}%")
