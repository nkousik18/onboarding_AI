"""
Temporary Streamlit UI for testing the chatbot.
Delete when done.

Run:
    /Users/Masters/Projects/Onboarding_AI/venv/bin/python3.12 -m streamlit run test_ui.py
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'chatbot'))

import streamlit as st

st.set_page_config(page_title="LIGHTHOUSE Chatbot Test", layout="centered")
st.title("LIGHTHOUSE — Chatbot Test")

# Load bot once per session
@st.cache_resource
def load_bot():
    from main import OnboardingChatbot
    return OnboardingChatbot(verbose=False)

with st.spinner("Loading chatbot..."):
    bot = load_bot()

st.success("Chatbot ready.")

# Suggested questions
with st.expander("Try these questions"):
    st.markdown("""
**Conflict queries**
- Are there any conflicting decisions?
- Does SQLAlchemy conflict with anything?

**Provenance queries**
- Where did the JWT decision come from?
- Trace the Tailwind CSS decision

**Decision queries**
- Why did we choose React?
- Why did we switch from Material UI to Tailwind?

**Person queries**
- What has Marcus been working on?
- Who worked on the frontend?

**Sprint queries**
- What's the summary of Sprint 1?
- List all decisions
    """)

# Chat history stored in session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Render existing messages
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg.get("meta"):
            st.caption(msg["meta"])

# Input
if prompt := st.chat_input("Ask anything about the project..."):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Get response
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = bot.chat(prompt)
        st.markdown(response.answer)
        meta = f"intent: `{response.intent}` · confidence: `{response.confidence:.2f}`"
        if response.sources:
            meta += f" · sources: {', '.join(response.sources[:3])}"
        st.caption(meta)

    st.session_state.messages.append({
        "role": "assistant",
        "content": response.answer,
        "meta": meta,
    })

# Sidebar controls
with st.sidebar:
    st.header("Controls")
    if st.button("Clear conversation"):
        bot.clear_history()
        st.session_state.messages = []
        st.rerun()

    st.divider()
    st.subheader("Session info")
    st.write(f"Turns: {bot.get_conversation_length()}")
    topic = bot.get_current_topic()
    st.write(f"Topic: {topic or '(none)'}")
