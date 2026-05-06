"""
Onboarding AI Chatbot - Main Entry Point (Conversational Version v3)

Fixes applied:
1. Topic command now works as CLI command
2. Better context retention for follow-ups
3. Improved person query handling
4. List all X queries support
5. Role/topic to person mapping
"""

from typing import Optional, List, Tuple, Dict
from dataclasses import dataclass, field
from datetime import datetime

# Handle both package import and direct execution
try:
    from .intent import IntentClassifier, ClassifiedIntent, IntentType
    from .retriever import SQLRetriever, Document
    from .context import ContextBuilder
    from .llm import BytezLLM
except ImportError:
    from intent import IntentClassifier, ClassifiedIntent, IntentType
    from retriever import SQLRetriever, Document
    from context import ContextBuilder
    from llm import BytezLLM




@dataclass
class Message:
    """A single message in the conversation."""
    role: str  # 'user' or 'assistant'
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    intent: str = None
    entities: List[str] = field(default_factory=list)
    topic: str = None
    
    def to_dict(self) -> Dict:
        return {
            'role': self.role,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'intent': self.intent,
            'entities': self.entities,
            'topic': self.topic
        }


class ConversationHistory:
    """
    Manages conversation history for multi-turn conversations.
    """
    
    MAX_HISTORY_TURNS = 10
    
    def __init__(self):
        self.messages: List[Message] = []
        self.current_topic: str = None
        self.current_entities: List[str] = []
        self.topic_stack: List[str] = []
        self.last_response_entities: List[str] = []  # NEW: Track entities mentioned in last response
    
    def add_user_message(self, content: str, intent: str = None, entities: List[str] = None, topic: str = None):
        """Add a user message to history."""
        if entities and len(entities) > 0:
            new_topic = entities[0]
            if new_topic and new_topic.lower() not in ['', 'none']:
                self.current_topic = new_topic
                self.current_entities = entities
                if not self.topic_stack or self.topic_stack[-1].lower() != new_topic.lower():
                    self.topic_stack.append(new_topic)
                    if len(self.topic_stack) > 5:
                        self.topic_stack = self.topic_stack[-5:]
        
        message = Message(
            role='user',
            content=content,
            intent=intent,
            entities=entities or [],
            topic=self.current_topic
        )
        self.messages.append(message)
        self._trim_history()
    
    def add_assistant_message(self, content: str, mentioned_entities: List[str] = None):
        """Add an assistant response to history."""
        message = Message(
            role='assistant',
            content=content,
            topic=self.current_topic
        )
        self.messages.append(message)
        
        # Track entities mentioned in response for follow-up questions
        if mentioned_entities:
            self.last_response_entities = mentioned_entities
        
        self._trim_history()
    
    def _trim_history(self):
        """Keep only recent messages."""
        max_messages = self.MAX_HISTORY_TURNS * 2
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]
    
    def get_context_summary(self) -> str:
        """Get a summary of recent conversation."""
        if not self.messages:
            return ""
        
        summary_parts = []
        recent = self.messages[-6:]
        
        for msg in recent:
            role = "User" if msg.role == 'user' else "Assistant"
            content = msg.content[:300] + "..." if len(msg.content) > 300 else msg.content
            summary_parts.append(f"{role}: {content}")
        
        return "\n".join(summary_parts)
    
    def get_last_assistant_response(self) -> Optional[str]:
        """Get the last assistant response for context."""
        for msg in reversed(self.messages):
            if msg.role == 'assistant':
                return msg.content
        return None
    
    def get_current_topic_context(self) -> str:
        """Get context about the current topic."""
        if not self.current_topic:
            return ""
        return f"Current topic: {self.current_topic}"
    
    def get_recent_entities(self) -> List[str]:
        """Get entities from recent conversation."""
        result = list(self.current_entities) if self.current_entities else []
        
        # Add entities from last response
        for entity in self.last_response_entities:
            if entity.lower() not in [e.lower() for e in result]:
                result.append(entity)
        
        # Add from recent messages
        seen = set(e.lower() for e in result)
        for msg in self.messages[-4:]:
            for entity in msg.entities:
                if entity.lower() not in seen:
                    result.append(entity)
                    seen.add(entity.lower())
        
        return result
    
    def resolve_references(self, query: str) -> Tuple[str, List[str]]:
        """Resolve pronouns and references."""
        query_lower = query.lower()
        inferred_entities = []
        
        reference_patterns = [
            'it', 'that', 'this', 'them', 'they', 'those',
            'that decision', 'the decision', 'that ticket', 'the ticket',
            'alternatives', 'who made', 'who decided', 'when was', 'why was',
            'tell me more', 'more about', 'what about', 'how about',
            'who wrote', 'who authored', 'the author', 'who created'
        ]
        
        has_reference = any(pattern in query_lower for pattern in reference_patterns)
        is_short_followup = len(query.split()) <= 6 and has_reference
        
        if (has_reference or is_short_followup) and self.current_entities:
            inferred_entities = self.current_entities.copy()
            
            # Also add entities from last response
            for entity in self.last_response_entities:
                if entity not in inferred_entities:
                    inferred_entities.append(entity)
            
            main_entity = self.current_entities[0]
            if main_entity and main_entity.lower() not in query_lower:
                return f"{query} (regarding: {main_entity})", inferred_entities
        
        return query, inferred_entities
    
    def get_last_topic(self) -> Optional[str]:
        """Get the current topic."""
        return self.current_topic
    
    def clear(self):
        """Clear conversation history."""
        self.messages = []
        self.current_topic = None
        self.current_entities = []
        self.topic_stack = []
        self.last_response_entities = []
    
    def __len__(self):
        return len(self.messages)


@dataclass
class ChatResponse:
    """Structured response from the chatbot."""
    answer: str
    intent: str
    confidence: float
    sources: List[str]
    entities: List[str]
    conversation_turn: int = 0
    
    def __str__(self):
        return self.answer


class OnboardingChatbot:
    """
    Main chatbot class with conversation memory.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        
        self._log("Initializing chatbot components...")
        
        self.classifier = IntentClassifier()
        self._log("  ✓ Intent Classifier loaded")
        
        self.retriever = SQLRetriever()
        self._log("  ✓ SQL Retriever loaded")
        
        self.context_builder = ContextBuilder()
        self._log("  ✓ Context Builder loaded")
        
        self.llm = BytezLLM()
        self._log("  ✓ LLM (Bytez/GPT-4o) loaded")
        
        self.history = ConversationHistory()
        self._log("  ✓ Conversation History initialized")
        
        self._log("Chatbot ready! (Conversational Mode v3)")
    
    def _log(self, message: str):
        if self.verbose:
            print(message)
    
    def _map_role_to_person(self, query: str, entities: List[str]) -> List[str]:
        """Map role/topic mentions to canonical person names via registry."""
        try:
            from retriever.people import registry
            matched = registry.find_by_role_keywords(query)
            return [p for p in matched if p not in entities]
        except Exception:
            return []

    def _extract_entities_from_response(self, response: str) -> List[str]:
        """Extract person names and ticket IDs from a response string."""
        entities = []

        try:
            from retriever.people import registry
            for name in registry.get_all_names():
                if name in response:
                    entities.append(name)
        except Exception:
            pass

        import re
        tickets = re.findall(r'ONBOARD-\d+', response)
        entities.extend(tickets)

        return entities
    
    def chat(self, query: str) -> ChatResponse:
        """Process a user query and return a response."""
        self._log(f"\n{'='*50}")
        self._log(f"Query: {query}")
        self._log(f"Turn: {len(self.history) // 2 + 1}")
        self._log(f"Current Topic: {self.history.get_last_topic()}")
        self._log('='*50)
        
        # Step 0: Resolve references
        resolved_query, inferred_entities = self.history.resolve_references(query)
        if resolved_query != query:
            self._log(f"\n0. Resolved: {resolved_query}")
            self._log(f"   Inferred entities: {inferred_entities}")
        
        # Step 1: Classify intent
        self._log("\n1. Classifying intent...")
        intent = self.classifier.classify(resolved_query)
        
        # Fix 2: low-confidence general follow-up — inherit previous intent/entities
        if (intent.intent_type == IntentType.GENERAL_QUERY and
                intent.confidence <= 0.4 and
                self.history.messages):
            for msg in reversed(self.history.messages):
                if msg.role == 'user' and msg.intent and msg.intent != 'general_query':
                    intent = ClassifiedIntent(
                        intent_type=IntentType(msg.intent),
                        confidence=0.75,
                        entities=intent.entities or msg.entities,
                        original_query=query
                    )
                    self._log(f"   [follow-up] Inherited intent '{msg.intent}' from history")
                    break

        # Combine entities
        all_entities = inferred_entities.copy()
        for e in intent.entities:
            if e not in all_entities:
                all_entities.append(e)

        # Map role/topic to person names
        role_persons = self._map_role_to_person(query, all_entities)
        all_entities.extend(role_persons)

        # Use current topic if no entities found — but don't bleed sprint numbers
        # into unrelated intents (e.g. asking "key decisions" after a sprint query)
        if not all_entities and self.history.current_topic:
            topic = self.history.current_topic
            is_sprint_intent = intent.intent_type in (
                IntentType.SPRINT_SUMMARY_QUERY, IntentType.STATUS_QUERY
            )
            if not (topic.isdigit() and not is_sprint_intent):
                all_entities = [topic]
        
        self._log(f"   Intent: {intent.intent_type.value}")
        self._log(f"   Confidence: {intent.confidence:.2f}")
        self._log(f"   All Entities: {all_entities}")
        
        # Step 2: Retrieve documents
        self._log("\n2. Retrieving documents...")
        documents = self.retriever.retrieve(
            query=resolved_query,
            intent_type=intent.intent_type.value,
            entities=all_entities,
            limit=5
        )
        self._log(f"   Found {len(documents)} documents")
        for doc in documents:
            self._log(f"   • {doc.source_type}: {doc.title[:40]}")
        
        # Step 3: Build context
        self._log("\n3. Building context...")
        context = self.context_builder.build_context(documents, intent.intent_type.value)
        
        # Add conversation history and last response for context
        history_summary = self.history.get_context_summary()
        topic_context = self.history.get_current_topic_context()
        last_response = self.history.get_last_assistant_response()

        # Only inject the last response verbatim when the current query looks like
        # a follow-up (short, uses reference words, or same intent as previous turn).
        # Avoids the LLM preferring stale sprint/person context over fresh retrieval.
        prev_intent = next(
            (m.intent for m in reversed(self.history.messages) if m.role == 'user' and m.intent),
            None
        )
        is_followup = (
            len(query.split()) <= 8 or
            prev_intent == intent.intent_type.value or
            any(w in query.lower() for w in ['more', 'details', 'tell me more', 'explain', 'elaborate'])
        )

        context_parts = []
        if topic_context:
            context_parts.append(topic_context)
        if history_summary:
            context_parts.append(f"PREVIOUS CONVERSATION:\n{history_summary}")
        if last_response and len(last_response) < 1000 and is_followup:
            context_parts.append(f"MY LAST RESPONSE (for follow-up context):\n{last_response[:800]}")
        context_parts.append(f"RELEVANT INFORMATION:\n{context}")
        
        full_context = "\n\n---\n\n".join(context_parts)
        
        self._log(f"   Context length: {len(full_context)} chars")
        
        # Step 4: Generate response
        self._log("\n4. Generating response...")
        
        # Real content = at least one non-error document
        # (a mix of valid + error docs is still answerable, e.g. sprint 2 found + sprint 3 not planned)
        has_real_content = any(not doc.metadata.get('error') for doc in documents)
        
        if has_real_content:
            prompt = self._build_conversational_prompt(full_context, query, intent.intent_type.value)
            answer = self.llm.generate(prompt)
        else:
            answer = self._generate_no_info_response(query, intent.intent_type.value, all_entities)
        
        self._log(f"   Response length: {len(answer)} chars")
        
        # Step 5: Extract entities from response for follow-up tracking
        response_entities = self._extract_entities_from_response(answer)
        
        # Step 6: Update history
        primary_topic = all_entities[0] if all_entities else None
        
        self.history.add_user_message(
            content=query,
            intent=intent.intent_type.value,
            entities=all_entities,
            topic=primary_topic
        )
        self.history.add_assistant_message(
            content=answer,
            mentioned_entities=response_entities
        )
        
        # Build response
        sources = list(set(
            f"{doc.source_type}:{doc.title[:30]}" 
            for doc in documents
            if not doc.metadata.get('error')
        ))
        
        return ChatResponse(
            answer=answer,
            intent=intent.intent_type.value,
            confidence=intent.confidence,
            sources=sources,
            entities=all_entities,
            conversation_turn=len(self.history) // 2
        )
    
    def _generate_no_info_response(self, query: str, intent_type: str, entities: List[str]) -> str:
        """Generate an honest response when no information is found."""
        
        entity_str = ", ".join(entities) if entities else "this topic"
        
        responses = {
            'status_query': f"I don't have specific status information about {entity_str} in my current data. You may want to check the project's Jira board for the most up-to-date ticket status.",
            
            'person_query': f"I don't have detailed information about {entity_str}'s contributions in my current data. The project tracking tools like Jira or GitHub would have the most accurate records.",
            
            'sprint_summary_query': f"I don't have detailed information about {entity_str} in my current data.",
            
            'ticket_query': f"I couldn't find information about {entity_str} in my current data. Please verify the ticket ID is correct.",
            
            'decision_query': f"I don't have specific information about decisions related to {entity_str} in my current data.",
            'conflict_query': "No conflicts have been detected between active decisions yet. Run check_conflicts.py to scan for them.",
            'provenance_query': f"I couldn't find a decision matching '{entity_str}'. Try using part of the decision title, e.g. 'trace the JWT decision' or 'where did Tailwind come from?'",
            'doc_drift_query': "The documentation drift check hasn't been run yet. Run `python scripts/check_confluence_drift.py` from the database/ directory to analyse doc staleness.",
            
            'meeting_query': f"I don't have information about meetings related to {entity_str} in my current data.",
            
            'howto_query': f"I don't have documentation about {entity_str} in my current data. Check the Confluence documentation for the most up-to-date guides.",
            
            'general_query': f"I don't have specific information about {entity_str} in my current data. Could you try rephrasing your question?",
        }
        
        return responses.get(intent_type, responses['general_query'])
    
    def _build_conversational_prompt(self, context: str, query: str, intent_type: str) -> str:
        """Build a prompt with conversation awareness."""
        
        intent_instructions = {
            'decision_query': "Focus on explaining the decision, its rationale, and alternatives considered.",
            'person_query': "Focus on the person's contributions, commits, tickets, and role in the project.",
            'timeline_query': "Focus on chronological order and key milestones.",
            'howto_query': "Focus on providing clear, step-by-step instructions.",
            'status_query': "Focus on current status of tickets, completion rates, and any blockers.",
            'ticket_query': "Focus on ticket details, related work, and current state.",
            'meeting_query': "Focus on what was discussed, decisions made, and action items.",
            'sprint_summary_query': "Provide a comprehensive sprint overview.",
            'list_query': "List all items requested with key details.",
            'conflict_query': "List every detected conflict clearly. For each conflict state: which two decisions conflict, the severity (high/medium/low), the conflict type (direct/indirect/potential), and a plain-English explanation of why they conflict. Be direct and structured.",
            'provenance_query': "Narrate the full provenance chain: where the decision came from, which Jira tickets followed, which commits implemented it, and any known conflicts. Tell the story chronologically in plain English.",
            'doc_drift_query': "Report which documentation pages are stale. For each page state its drift risk (HIGH/MEDIUM/LOW/NONE), when it was last updated, when the related code was last changed, and the gap in days. Highlight high-risk pages first and explain why they may be out of date.",
            'general_query': "Provide helpful information based on the context.",
        }
        
        instruction = intent_instructions.get(intent_type, intent_instructions['general_query'])
        
        topic_instruction = ""
        if self.history.current_topic:
            topic_instruction = f"\nCURRENT TOPIC: '{self.history.current_topic}'. References like 'it', 'that', 'the author', 'who wrote it' refer to this topic."
        
        prompt = f"""You are an AI assistant for the Employee Onboarding Portal project.

INSTRUCTIONS: {instruction}
{topic_instruction}

CRITICAL RULES:
1. ONLY answer based on the provided context - DO NOT make up information
2. If the context mentions a person name, ticket ID, or fact, you can repeat it
3. NEVER invent commit SHAs, ticket IDs, dates, or names not in the context
4. For follow-up questions like "who wrote it?", look in the context AND in "MY LAST RESPONSE" section
5. If you mentioned something in your last response and user asks about it, you can reference that
6. Be concise but complete

CONTEXT:
{context}

QUESTION: {query}

Answer based ONLY on the information above:"""
        
        return prompt
    
    def chat_simple(self, query: str) -> str:
        """Simple chat interface."""
        return self.chat(query).answer
    
    def get_intent(self, query: str) -> Tuple[str, float, List[str]]:
        """Get intent classification."""
        intent = self.classifier.classify(query)
        return (intent.intent_type.value, intent.confidence, intent.entities)
    
    def clear_history(self):
        """Clear conversation history."""
        self.history.clear()
        self._log("Conversation history cleared.")
    
    def get_conversation_length(self) -> int:
        """Get the number of turns."""
        return len(self.history) // 2
    
    def get_current_topic(self) -> Optional[str]:
        """Get current topic."""
        return self.history.get_last_topic()
    
    def get_current_entities(self) -> List[str]:
        """Get current entities."""
        return self.history.current_entities
    
    def health_check(self) -> dict:
        """Check component status."""
        status = {
            'classifier': 'ok',
            'retriever': 'ok',
            'context_builder': 'ok',
            'llm': self.llm.health_check(),
            'conversation_history': f'{len(self.history)} messages',
            'current_topic': self.history.get_last_topic()
        }
        
        try:
            docs = self.retriever.retrieve("test", "general_query", [], limit=1)
            status['retriever'] = 'ok'
        except Exception as e:
            status['retriever'] = f'error: {str(e)}'
        
        return status


# =========================================
# INTERACTIVE CLI
# =========================================

def run_interactive():
    """Run an interactive chat session."""
    print("=" * 60)
    print("🤖 ONBOARDING AI CHATBOT (Conversational v3)")
    print("=" * 60)
    print("\nWelcome! I remember our conversation.")
    print("\nCommands:")
    print("  'quit'   - Exit")
    print("  'help'   - Example questions")
    print("  'clear'  - Clear history")
    print("  'debug'  - Toggle debug mode")
    print("  'topic'  - Show current topic")
    print("  'status' - Show bot status")
    print("")
    
    bot = OnboardingChatbot(verbose=False)
    
    health = bot.health_check()
    if health['llm']['status'] != 'ok':
        print(f"⚠️  Warning: LLM issue: {health['llm']['message']}")
    
    while True:
        try:
            turn = bot.get_conversation_length() + 1
            query = input(f"\n👤 You (turn {turn}): ").strip()
            
            if not query:
                continue
            
            # ========== CLI COMMANDS (checked BEFORE chat) ==========
            if query.lower() == 'quit':
                print("\n👋 Goodbye!")
                break
            
            if query.lower() == 'help':
                print_help()
                continue
            
            if query.lower() == 'clear':
                bot.clear_history()
                print("🗑️  History cleared!")
                continue
            
            if query.lower() == 'debug':
                bot.verbose = not bot.verbose
                print(f"🔧 Debug: {'ON' if bot.verbose else 'OFF'}")
                continue
            
            if query.lower() == 'topic':
                topic = bot.get_current_topic()
                entities = bot.get_current_entities()
                print(f"\n📌 Current topic: {topic or '(none)'}")
                print(f"📌 Current entities: {entities or '(none)'}")
                print(f"📌 Conversation turns: {bot.get_conversation_length()}")
                continue
            
            if query.lower() == 'status':
                health = bot.health_check()
                print("\n📊 Bot Status:")
                for k, v in health.items():
                    print(f"   {k}: {v}")
                continue
            
            # ========== NORMAL CHAT ==========
            print("\n🤖 Assistant: ", end="")
            response = bot.chat(query)
            print(response.answer)
            
            print(f"\n   [Intent: {response.intent} | Sources: {', '.join(response.sources[:3]) if response.sources else 'none'}]")
            
        except KeyboardInterrupt:
            print("\n\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")
            import traceback
            traceback.print_exc()


def print_help():
    """Print example questions."""
    print("\n" + "=" * 50)
    print("📖 EXAMPLE QUESTIONS")
    print("=" * 50)
    
    examples = [
        ("Decision queries:", [
            "Why did we choose React?",
            "Who made that decision?",
            "What alternatives were considered?",
        ]),
        ("Person queries:", [
            "What has Marcus been working on?",
            "Who worked on the frontend?",
            "Show me Lisa's commits",
        ]),
        ("Sprint queries:", [
            "What's the summary of Sprint 1?",
            "What's the status of Sprint 2?",
        ]),
        ("List queries:", [
            "What Confluence pages are available?",
            "List all decisions",
        ]),
        ("Conflict queries:", [
            "Are there any conflicting decisions?",
            "Does SQLAlchemy conflict with anything?",
            "Show me architectural conflicts",
        ]),
        ("Provenance queries:", [
            "Where did the JWT decision come from?",
            "Trace the Tailwind CSS decision",
            "Show me the history behind SQLAlchemy",
        ]),
    ]
    
    for category, questions in examples:
        print(f"\n{category}")
        for q in questions:
            print(f"  • {q}")
    
    print("\n" + "=" * 50)


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        print("Running tests...")
        bot = OnboardingChatbot(verbose=True)
        
        # Test person query
        print("\n--- Test: Person Query ---")
        r = bot.chat("What has Marcus been working on?")
        print(f"Answer: {r.answer[:300]}...")
        
        # Test frontend mapping
        print("\n--- Test: Frontend Role Mapping ---")
        bot.clear_history()
        r = bot.chat("Who worked on the frontend?")
        print(f"Answer: {r.answer[:300]}...")
        
    else:
        run_interactive()
