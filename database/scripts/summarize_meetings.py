"""
Meeting Summarization Script

Reads raw VTT transcripts from the meetings table and fills in summary,
key_decisions, and action_items using Groq (llama-3.3-70b-versatile).

Usage:
    python scripts/summarize_meetings.py --all
    python scripts/summarize_meetings.py --meeting-id <uuid>
    python scripts/summarize_meetings.py --force    # reprocess all
    python scripts/summarize_meetings.py --dry-run

Requirements:
    GROQ_API_KEY in database/.env
"""

import os
import sys
import json
import re
import argparse
from dataclasses import dataclass
from typing import List, Optional, Any

# Add the parent directory to path for Django
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.db import transaction
from knowledge_base.models import Meeting

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI


# ============================================
# GROQ LLM BACKEND (OpenAI-compatible)
# ============================================

GROQ_API_KEY = os.getenv('GROQ_API_KEY')
GROQ_MODEL   = "llama-3.3-70b-versatile"


class BytezLM:
    """Groq backend, drop-in replacement for the old Bytez wrapper."""

    def __init__(self, model_name: str = GROQ_MODEL, api_key: str = None):
        self.model_name = model_name
        self.client = OpenAI(
            api_key=api_key or GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )

    def __call__(self, prompt: str, **kwargs) -> str:
        return self.generate(prompt)

    def generate(self, prompt: str, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )
        return response.choices[0].message.content


# ============================================
# DSPy-STYLE SIGNATURES
# ============================================

@dataclass
class InputField:
    """DSPy-style input field descriptor."""
    desc: str = ""
    prefix: str = ""


@dataclass
class OutputField:
    """DSPy-style output field descriptor."""
    desc: str = ""
    prefix: str = ""


class Signature:
    """
    DSPy-style Signature base class.
    Defines the input/output contract for a module.
    """
    
    @classmethod
    def get_input_fields(cls) -> dict:
        """Get all input fields from the signature."""
        fields = {}
        for name, value in cls.__dict__.items():
            if isinstance(value, InputField):
                fields[name] = value
        return fields
    
    @classmethod
    def get_output_fields(cls) -> dict:
        """Get all output fields from the signature."""
        fields = {}
        for name, value in cls.__dict__.items():
            if isinstance(value, OutputField):
                fields[name] = value
        return fields
    
    @classmethod
    def get_docstring(cls) -> str:
        """Get the signature's docstring."""
        return cls.__doc__ or ""


class MeetingSummary(Signature):
    """Generate a concise 2-3 paragraph summary of the meeting discussion."""
    
    transcript = InputField(desc="The meeting transcript")
    meeting_title = InputField(desc="Title of the meeting")
    participants = InputField(desc="List of participants")
    
    summary = OutputField(desc="A 2-3 paragraph summary of the meeting")


class KeyDecisions(Signature):
    """Extract key decisions made during the meeting."""
    
    transcript = InputField(desc="The meeting transcript")
    meeting_title = InputField(desc="Title of the meeting")
    
    decisions = OutputField(desc="List of key decisions with rationale")


class ActionItems(Signature):
    """Extract action items and assigned tasks from the meeting."""
    
    transcript = InputField(desc="The meeting transcript")
    meeting_title = InputField(desc="Title of the meeting")
    
    action_items = OutputField(desc="List of action items with assignees")


class FullMeetingAnalysis(Signature):
    """Analyze a meeting transcript to extract summary, decisions, and action items."""
    
    transcript = InputField(desc="The full meeting transcript")
    meeting_title = InputField(desc="Title of the meeting")
    participants = InputField(desc="Comma-separated list of participants")
    
    summary = OutputField(desc="A 2-3 paragraph summary")
    key_decisions = OutputField(desc="JSON array of key decisions")
    action_items = OutputField(desc="JSON array of action items with assignees")


# ============================================
# DSPy-STYLE MODULES
# ============================================

@dataclass
class Prediction:
    """DSPy-style prediction result."""
    
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def __repr__(self):
        attrs = ', '.join(f"{k}={repr(v)[:50]}" for k, v in self.__dict__.items())
        return f"Prediction({attrs})"


class Module:
    """DSPy-style Module base class."""
    
    def __init__(self):
        self.lm = None
    
    def __call__(self, **kwargs) -> Prediction:
        return self.forward(**kwargs)
    
    def forward(self, **kwargs) -> Prediction:
        raise NotImplementedError


class Predict(Module):
    """
    DSPy-style Predict module.
    Takes a signature and generates outputs based on inputs.
    """
    
    def __init__(self, signature: type):
        super().__init__()
        self.signature = signature
    
    def forward(self, lm: BytezLM, **kwargs) -> Prediction:
        """Generate prediction using the signature."""
        prompt = self._build_prompt(**kwargs)
        response = lm.generate(prompt)
        outputs = self._parse_response(response)
        return Prediction(**outputs)
    
    def _build_prompt(self, **kwargs) -> str:
        """Build prompt from signature and inputs."""
        parts = []
        
        # Add task description from docstring
        parts.append(f"Task: {self.signature.get_docstring()}")
        parts.append("")
        
        # Add inputs
        parts.append("Inputs:")
        for name, field in self.signature.get_input_fields().items():
            value = kwargs.get(name, "")
            parts.append(f"- {name}: {value}")
        parts.append("")
        
        # Add output instructions
        parts.append("Outputs (provide each on a new line with the field name):")
        for name, field in self.signature.get_output_fields().items():
            parts.append(f"- {name}: {field.desc}")
        
        return "\n".join(parts)
    
    def _parse_response(self, response: str) -> dict:
        """Parse LLM response into output fields."""
        outputs = {}
        output_fields = self.signature.get_output_fields()
        
        for name in output_fields:
            # Try to find the field in response
            pattern = rf"{name}:\s*(.+?)(?=\n\w+:|$)"
            match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)
            if match:
                outputs[name] = match.group(1).strip()
            else:
                outputs[name] = ""
        
        return outputs


class ChainOfThought(Module):
    """
    DSPy-style ChainOfThought module.
    Adds reasoning steps before generating outputs.
    """
    
    def __init__(self, signature: type):
        super().__init__()
        self.signature = signature
    
    def forward(self, lm: BytezLM, **kwargs) -> Prediction:
        """Generate prediction with chain of thought reasoning."""
        prompt = self._build_prompt(**kwargs)
        response = lm.generate(prompt)
        outputs = self._parse_response(response)
        return Prediction(**outputs)
    
    def _build_prompt(self, **kwargs) -> str:
        """Build CoT prompt from signature and inputs."""
        parts = []
        
        # Task description
        parts.append(f"Task: {self.signature.get_docstring()}")
        parts.append("")
        
        # Inputs
        for name, field in self.signature.get_input_fields().items():
            value = kwargs.get(name, "")
            if name == "transcript":
                # Truncate long transcripts
                value = value[:12000] if len(value) > 12000 else value
            parts.append(f"{name.upper()}: {value}")
            parts.append("")
        
        # Chain of thought instruction
        parts.append("Let's think step by step:")
        parts.append("1. First, identify the main topics discussed")
        parts.append("2. Note any decisions that were made")
        parts.append("3. List any tasks or action items assigned")
        parts.append("")
        
        # Output format
        parts.append("Now provide your analysis in this exact JSON format:")
        parts.append("{")
        for name, field in self.signature.get_output_fields().items():
            if "array" in field.desc.lower() or "list" in field.desc.lower():
                parts.append(f'  "{name}": ["item1", "item2", ...],')
            else:
                parts.append(f'  "{name}": "your {name} here",')
        parts.append("}")
        
        return "\n".join(parts)
    
    def _parse_response(self, response: str) -> dict:
        """Parse CoT response into output fields."""
        outputs = {}
        output_fields = self.signature.get_output_fields()
        
        # Try to extract JSON from response
        json_match = re.search(r'\{[^{}]*\}', response, re.DOTALL)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                for name in output_fields:
                    if name in parsed:
                        outputs[name] = parsed[name]
                return outputs
            except json.JSONDecodeError:
                pass
        
        # Fallback: extract fields individually
        for name, field in output_fields.items():
            if "array" in field.desc.lower() or "list" in field.desc.lower():
                # Try to find JSON array
                array_match = re.search(rf'"{name}"\s*:\s*(\[[^\]]*\])', response, re.DOTALL)
                if array_match:
                    try:
                        outputs[name] = json.loads(array_match.group(1))
                    except:
                        outputs[name] = []
                else:
                    outputs[name] = []
            else:
                # Try to find string value
                str_match = re.search(rf'"{name}"\s*:\s*"([^"]*)"', response, re.DOTALL)
                if str_match:
                    outputs[name] = str_match.group(1)
                else:
                    outputs[name] = ""
        
        return outputs


# ============================================
# MEETING SUMMARIZER (DSPy-STYLE PIPELINE)
# ============================================

class MeetingSummarizer(Module):
    """
    DSPy-style module for meeting summarization.
    Composes multiple sub-modules into a pipeline.
    """
    
    def __init__(self, lm: BytezLM):
        super().__init__()
        self.lm = lm
        
        # Sub-modules using ChainOfThought for better reasoning
        self.analyzer = ChainOfThought(FullMeetingAnalysis)
    
    def forward(self, transcript: str, meeting_title: str, participants: str) -> Prediction:
        """
        Run the full meeting analysis pipeline.
        
        Args:
            transcript: Cleaned meeting transcript
            meeting_title: Title of the meeting
            participants: Comma-separated participant names
        
        Returns:
            Prediction with summary, key_decisions, action_items
        """
        # Run chain of thought analysis
        result = self.analyzer.forward(
            self.lm,
            transcript=transcript,
            meeting_title=meeting_title,
            participants=participants
        )
        
        # Ensure outputs are properly formatted
        summary = result.summary if hasattr(result, 'summary') else ""
        key_decisions = result.key_decisions if hasattr(result, 'key_decisions') else []
        action_items = result.action_items if hasattr(result, 'action_items') else []
        
        # Convert to lists if strings
        if isinstance(key_decisions, str):
            key_decisions = self._parse_list(key_decisions)
        if isinstance(action_items, str):
            action_items = self._parse_list(action_items)
        
        return Prediction(
            summary=summary,
            key_decisions=key_decisions,
            action_items=action_items
        )
    
    def _parse_list(self, text: str) -> list:
        """Parse a string that might be a list."""
        if not text:
            return []
        
        # Try JSON parse
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
        except:
            pass
        
        # Split by newlines or bullets
        items = []
        for line in text.split('\n'):
            line = line.strip()
            line = re.sub(r'^[-•*]\s*', '', line)
            line = re.sub(r'^\d+\.\s*', '', line)
            if line and len(line) > 5:
                items.append(line)
        
        return items


# ============================================
# HELPER FUNCTIONS
# ============================================

def clean_vtt_transcript(vtt_content: str) -> str:
    """Clean VTT content to extract just the dialogue."""
    lines = vtt_content.split('\n')
    cleaned_lines = []
    
    for line in lines:
        line = line.strip()
        
        if not line:
            continue
        if line == 'WEBVTT':
            continue
        if line.startswith('NOTE'):
            continue
        if re.match(r'\d{2}:\d{2}:\d{2}', line):
            continue
        if line.startswith(('Meeting:', 'Date:', 'Duration:', 'Participants:')):
            continue
        
        cleaned_lines.append(line)
    
    return '\n'.join(cleaned_lines)


def extract_participants_from_vtt(vtt_content: str) -> list:
    """Extract participant names from VTT content."""
    participants = set()
    
    # From NOTE section
    match = re.search(r'Participants:\s*(.+)', vtt_content)
    if match:
        for part in match.group(1).split(','):
            name = re.sub(r'\s*\([^)]*\)', '', part).strip()
            if name:
                participants.add(name)
    
    # From dialogue
    for line in vtt_content.split('\n'):
        match = re.match(r'^([A-Za-z\s\']+):', line.strip())
        if match:
            speaker = match.group(1).strip()
            if not re.match(r'^\d', speaker) and len(speaker) > 1:
                participants.add(speaker)
    
    return list(participants)


# ============================================
# MAIN PROCESSING
# ============================================

def summarize_meeting(meeting: Meeting, summarizer: MeetingSummarizer, verbose: bool = True) -> dict:
    """Summarize a single meeting using DSPy-style pipeline."""
    
    if verbose:
        print(f"\n{'='*60}")
        print(f"Processing: {meeting.title}")
        print(f"{'='*60}")
    
    # Clean transcript
    cleaned_transcript = clean_vtt_transcript(meeting.raw_vtt_content)
    
    # Get participants
    if meeting.participants:
        try:
            participants = json.loads(meeting.participants)
            participants_str = ', '.join(participants)
        except:
            participants_str = meeting.participants
    else:
        participants = extract_participants_from_vtt(meeting.raw_vtt_content)
        participants_str = ', '.join(participants)
    
    if verbose:
        print(f"Participants: {participants_str}")
        print(f"Transcript length: {len(cleaned_transcript)} chars")
        print(f"\nRunning DSPy ChainOfThought analysis...")
    
    # Run DSPy-style pipeline
    result = summarizer(
        transcript=cleaned_transcript,
        meeting_title=meeting.title or "Team Meeting",
        participants=participants_str
    )
    
    if verbose:
        print(f"\n--- Summary ---")
        summary = result.summary or ""
        print(summary[:500] + "..." if len(summary) > 500 else summary)
        
        print(f"\n--- Key Decisions ({len(result.key_decisions)}) ---")
        for i, decision in enumerate(result.key_decisions[:5], 1):
            print(f"  {i}. {decision}")
        
        print(f"\n--- Action Items ({len(result.action_items)}) ---")
        for i, item in enumerate(result.action_items[:5], 1):
            print(f"  {i}. {item}")
    
    return {
        'summary': result.summary,
        'key_decisions': result.key_decisions,
        'action_items': result.action_items
    }


def update_meeting_in_db(meeting: Meeting, analysis: dict):
    """Update the meeting record with analysis results."""
    with transaction.atomic():
        meeting.summary = analysis['summary']
        meeting.key_decisions = json.dumps(analysis['key_decisions'])
        meeting.action_items = json.dumps(analysis['action_items'])
        meeting.save()


# ============================================
# CLI
# ============================================

def main():
    parser = argparse.ArgumentParser(description='Summarize meeting transcripts using Groq')
    parser.add_argument('--meeting-id', type=str, help='Process specific meeting')
    parser.add_argument('--all', action='store_true', help='Process all without summaries')
    parser.add_argument('--force', action='store_true', help='Reprocess all')
    parser.add_argument('--model', type=str, default='llama-3.3-70b-versatile', help='Model name')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    
    args = parser.parse_args()
    
    # Setup
    print("="*60)
    print("Meeting Summarizer (Groq / llama-3.3-70b-versatile)")
    print("="*60)
    print(f"\nInitializing Groq client...")
    print(f"  API Key: {GROQ_API_KEY[:10]}...")
    print(f"  Model: {args.model}")
    
    # Initialize DSPy-style components
    lm = BytezLM(model_name=args.model)
    summarizer = MeetingSummarizer(lm=lm)
    
    print(f"\nDSPy Modules loaded:")
    print(f"  - ChainOfThought(FullMeetingAnalysis)")
    print(f"  - Signature fields: transcript, meeting_title, participants")
    print(f"  - Output fields: summary, key_decisions, action_items")
    
    # Get meetings
    if args.meeting_id:
        try:
            meetings = [Meeting.objects.get(id=args.meeting_id)]
        except Meeting.DoesNotExist:
            print(f"Meeting not found: {args.meeting_id}")
            sys.exit(1)
    elif args.all:
        if args.force:
            meetings = list(Meeting.objects.all())
        else:
            meetings = list(
                Meeting.objects.filter(summary__isnull=True) | 
                Meeting.objects.filter(summary='')
            )
    else:
        # Show available
        meetings = Meeting.objects.all()
        print("\nAvailable meetings:")
        print("-" * 60)
        for m in meetings:
            status = "✓" if m.summary else "✗"
            print(f"  [{status}] {m.id}")
            print(f"      {m.title}")
        print("-" * 60)
        print(f"\nTotal: {meetings.count()}")
        without = Meeting.objects.filter(summary__isnull=True).count()
        without += Meeting.objects.filter(summary='').count()
        print(f"Without summary: {without}")
        print("\nUsage:")
        print("  --all              Process all without summaries")
        print("  --all --force      Reprocess all")
        print("  --meeting-id X     Process specific meeting")
        print("  --dry-run          Preview only")
        return
    
    if not meetings:
        print("No meetings to process")
        return
    
    print(f"\nProcessing {len(meetings)} meeting(s)...")
    
    processed = 0
    errors = 0
    
    for meeting in meetings:
        try:
            analysis = summarize_meeting(meeting, summarizer, verbose=True)
            
            if not args.dry_run:
                update_meeting_in_db(meeting, analysis)
                print(f"\n✓ Saved to database")
            else:
                print(f"\n[DRY RUN] Would save to database")
            
            processed += 1
            
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            errors += 1
    
    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"  Processed: {processed}")
    print(f"  Errors:    {errors}")


if __name__ == '__main__':
    main()