
import os
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
st.write("ارفع درسك، احصل على ملخص، واختبر معلوماتك بالذكاء الاصطناعي.")

api_key = st.text_input(
    "أدخل مفتاح Gemini API",
    type="password"
)

uploaded_file = st.file_uploader(
    "اختر ملف الدرس بصيغة PDF",
    type=["pdf"]
)

if uploaded_file and st.button("📚 تحليل الدرس"):
    if not api_key:
        st.error("أدخل مفتاح Gemini API أولًا.")
        st.stop()

    try:
        client = genai.Client(api_key=api_key)

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
                "يبدو أن الملف ممسوح ضوئيًا. "
                "هذه النسخة تحتاج إلى إضافة OCR لقراءته."
            )
            st.stop()

        with st.spinner("جارٍ تلخيص الدرس..."):
            summary_response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                contents=(
                    "لخّص الدرس التالي باللغة العربية، "
                    "مع تنظيم الأفكار والعناوين:\n\n"
                    + lesson_text[:18000]
                )
            )
            summary = summary_response.text

        st.session_state["summary"] = summary
        st.session_state["lesson_text"] = lesson_text

        st.success("تم تحليل الدرس بنجاح!")

    except Exception as e:
        st.error(f"حدث خطأ: {e}")

if "summary" in st.session_state:
    st.subheader("📝 ملخص الدرس")
    st.markdown(st.session_state["summary"])

    if st.button("🧠 إنشاء اختبار من 10 أسئلة"):
        try:
            client = genai.Client(api_key=api_key)

            prompt = f"""
أنشئ 10 أسئلة اختيار من متعدد باللغة العربية
اعتمادًا على الدرس التالي.

أعد JSON صالحًا فقط بهذا الشكل:
{{
  "questions": [
    {{
      "question": "نص السؤال",
      "options": ["أ", "ب", "ج", "د"],
      "correct_answer": 0,
      "explanation": "شرح الإجابة"
    }}
  ]
}}

correct_answer هو رقم الإجابة الصحيحة بدءًا من الصفر.
كل سؤال له أربعة خيارات وإجابة صحيحة واحدة.

الدرس:
{st.session_state["summary"][:9000]}
"""
            with st.spinner("جارٍ إنشاء الأسئلة..."):
                response = client.models.generate_content(
                    model="gemini-3.5-flash-lite",
                    contents=prompt
                )

            raw = response.text.strip()
            raw = raw.replace("```json", "").replace("```", "").strip()
            quiz = json.loads(raw)

            st.session_state["quiz"] = quiz["questions"]
            st.session_state["answers"] = {}

        except Exception as e:
            st.error(f"تعذر إنشاء الاختبار: {e}")

if "quiz" in st.session_state:
    st.subheader("🧠 اختبر معلوماتك")

    with st.form("quiz_form"):
        for i, q in enumerate(st.session_state["quiz"]):
            st.markdown(f"**السؤال {i + 1}: {q['question']}**")
            answer = st.radio(
                "اختر إجابتك:",
                options=range(len(q["options"])),
                format_func=lambda x, opts=q["options"]: opts[x],
                key=f"answer_{i}"
            )
            st.session_state["answers"][i] = answer

        submitted = st.form_submit_button("✅ تصحيح الاختبار")

    if submitted:
        score = 0

        for i, q in enumerate(st.session_state["quiz"]):
            selected = st.session_state["answers"][i]
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

        st.subheader(
            f"🎯 نتيجتك: {score} / {len(st.session_state['quiz'])}"
        )
