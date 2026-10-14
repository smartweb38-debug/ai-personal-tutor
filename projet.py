
import json
import streamlit as st
import fitz
from google import genai

st.set_page_config(
    page_title="المدرس الشخصي الذكي",
    page_icon="🎓",
    layout="centered"
)

st.title("🎓 المدرس الشخصي الذكي")
st.write(
    "ارفع درسك، احصل على ملخص، "
    "واختبر معلوماتك بالذكاء الاصطناعي."
)

try:
    api_key = st.secrets["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)
except Exception:
    st.error(
        "لم يتم إعداد مفتاح Gemini بشكل صحيح. "
        "يرجى مراجعة إعدادات التطبيق."
    )
    st.stop()

uploaded_file = st.file_uploader(
    "اختر ملف الدرس بصيغة PDF",
    type=["pdf"]
)

if uploaded_file and st.button("📚 تحليل الدرس"):
    try:
        with st.spinner("جارٍ استخراج النص من الملف..."):
            document = fitz.open(
                stream=uploaded_file.getvalue(),
                filetype="pdf"
            )
            lesson_text = "\n".join(
                page.get_text() for page in document
            )

        if len(lesson_text.strip()) < 100:
            st.warning(
                "لم نستطع استخراج نص كافٍ. "
                "قد يكون الملف ممسوحًا ضوئيًا؛ "
                "سنضيف دعم OCR لاحقًا."
            )
            st.stop()

        with st.spinner("جارٍ تلخيص الدرس..."):
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=(
                    "لخّص الدرس التالي باللغة العربية، "
                    "مع تنظيم الأفكار والعناوين:\n\n"
                    + lesson_text[:18000]
                )
            )

        summary = response.text
        if not summary:
            st.error("لم يُرجع النموذج ملخصًا. حاول مرة أخرى.")
            st.stop()

        st.session_state["summary"] = summary
        st.session_state["quiz"] = None

        st.success("تم تحليل الدرس بنجاح!")

    except Exception as e:
        st.error(f"حدث خطأ أثناء تحليل الدرس: {e}")

if st.session_state.get("summary"):
    st.subheader("📝 ملخص الدرس")
    st.markdown(st.session_state["summary"])

    if st.button("🧠 إنشاء اختبار من 10 أسئلة"):
        prompt = f"""
أنشئ 10 أسئلة اختيار من متعدد باللغة العربية اعتمادًا
على الدرس التالي. أعد JSON صالحًا فقط بهذا الشكل:
{{
  "questions": [
    {{
      "question": "نص السؤال",
      "options": ["الخيار الأول", "الخيار الثاني", "الخيار الثالث", "الخيار الرابع"],
      "correct_answer": 0,
      "explanation": "شرح الإجابة"
    }}
  ]
}}
يجب أن يحتوي كل سؤال على أربعة خيارات.
correct_answer هو فهرس الإجابة الصحيحة بدءًا من الصفر.

الدرس:
{st.session_state["summary"][:9000]}
"""
        try:
            with st.spinner("جارٍ إنشاء الأسئلة..."):
                response = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=prompt
                )

            raw = (response.text or "").strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            quiz_data = json.loads(raw)
            questions = quiz_data["questions"]

            if len(questions) != 10:
                raise ValueError("لم يُنشأ العدد المطلوب من الأسئلة.")

            for q in questions:
                if (
                    len(q["options"]) != 4
                    or q["correct_answer"] not in range(4)
                ):
                    raise ValueError("تنسيق أحد الأسئلة غير صحيح.")

            st.session_state["quiz"] = questions
            st.session_state["quiz_submitted"] = False

        except Exception as e:
            st.error(f"تعذر إنشاء الاختبار: {e}")

if st.session_state.get("quiz"):
    questions = st.session_state["quiz"]
    st.subheader("🧠 اختبر معلوماتك")

    with st.form("quiz_form"):
        answers = {}

        for i, q in enumerate(questions):
            st.markdown(f"**السؤال {i + 1}: {q['question']}**")
            answers[i] = st.radio(
                "اختر إجابتك:",
                options=range(4),
                format_func=lambda x, opts=q["options"]: opts[x],
                key=f"answer_{i}",
                index=None
            )

        submitted = st.form_submit_button("✅ تصحيح الاختبار")

    if submitted:
        if any(a is None for a in answers.values()):
            st.warning("أجب عن جميع الأسئلة أولًا.")
        else:
            score = 0

            for i, q in enumerate(questions):
                selected = answers[i]
                correct = q["correct_answer"]

                if selected == correct:
                    score += 1
                    st.success(f"السؤال {i + 1}: إجابة صحيحة!")
                else:
                    st.error(
                        f"السؤال {i + 1}: الإجابة الصحيحة هي "
                        f"{q['options'][correct]}"
                    )

                st.write(q["explanation"])

            st.subheader(f"🎯 نتيجتك: {score} / {len(questions)}")
            st.progress(score / len(questions))
