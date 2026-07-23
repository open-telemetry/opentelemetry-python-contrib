# Copyright The OpenTelemetry Authors
# SPDX-License-Identifier: Apache-2.0

import os

from crewai import Agent, Crew, Process, Task
from crewai.tools import BaseTool
from pydantic import BaseModel, Field


class WordCountInput(BaseModel):
    text: str = Field(description="The text to count words in.")


class WordCountTool(BaseTool):
    name: str = "word_count"
    description: str = "Counts the number of words in a piece of text."
    args_schema: type[BaseModel] = WordCountInput

    def _run(self, text: str) -> str:
        return f"{len(text.split())} words"


def build_crew() -> Crew:
    researcher = Agent(
        role="Researcher",
        goal="Produce a short, factual note about the given topic.",
        backstory="A concise research analyst who writes brief, factual notes with no filler.",
        tools=[WordCountTool()],
    )

    writer = Agent(
        role="Writer",
        goal="Turn a research note into a two-sentence summary.",
        backstory="A summarizer who writes exactly two plain sentences.",
    )

    research_task = Task(
        description=(
            "Write a 3-sentence factual note about {topic}. Then use the "
            "word_count tool to report how many words your note has."
        ),
        expected_output="A 3-sentence note about {topic}, plus its word count.",
        agent=researcher,
    )

    writing_task = Task(
        description=(
            "Using the research note above, write exactly two plain "
            "sentences summarizing {topic} for a general audience."
        ),
        expected_output="A two-sentence plain-language summary of {topic}.",
        agent=writer,
        context=[research_task],
    )

    return Crew(
        agents=[researcher, writer],
        tasks=[research_task, writing_task],
        process=Process.sequential,
    )


def main():
    os.environ.setdefault(
        "OPENAI_MODEL_NAME", os.environ.get("CHAT_MODEL", "gpt-4o-mini")
    )
    crew = build_crew()
    result = crew.kickoff(inputs={"topic": "the history of the paperclip"})
    print(result)


if __name__ == "__main__":
    main()
