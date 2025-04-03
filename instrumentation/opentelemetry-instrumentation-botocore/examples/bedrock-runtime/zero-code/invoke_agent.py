#!/usr/bin/env python3

import boto3
import json
import uuid
import logging
from botocore.exceptions import ClientError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class WeatherAgentDemo:
    def __init__(self):
        # Initialize Bedrock Agents Runtime client
        self.client = boto3.client('bedrock-agent-runtime')

        # Replace these with your actual agent IDs
        self.agent_id = "TFMZVIWXR7"
        self.agent_alias_id = "ZT7YYHO8TO"

        # Generate a unique session ID for this conversation
        self.session_id = str(uuid.uuid4())

    def invoke_agent(self, input_text, session_state=None, end_session=False):
        """Invoke the Bedrock agent with various features enabled."""
        try:
            # Prepare the request parameters
            request_params = {
                "agentId": self.agent_id,
                "agentAliasId": self.agent_alias_id,
                "sessionId": self.session_id,
                "inputText": input_text,
                "enableTrace": True,  # Enable tracing for debugging
                "endSession": end_session,
            }

            # Add session state if provided (for returning control results)
            if session_state:
                request_params["sessionState"] = session_state

            # Invoke the agent
            response = self.client.invoke_agent(**request_params)

            # Process the streaming response
            completion = ""
            trace_data = []

            for event in response.get("completion"):
                if "chunk" in event:
                    chunk = event["chunk"]
                    completion += chunk["bytes"].decode()
                elif "trace" in event:
                    trace_data.append(event["trace"])
                elif "returnControl" in event:
                    # Handle the case where the agent returns control
                    return {"type": "return_control", "data": event["returnControl"]}

            return {
                "type": "completion",
                "completion": completion,
                "trace": trace_data
            }

        except ClientError as e:
            logger.error(f"Error invoking agent: {e}")
            raise

    def handle_return_control(self, return_control_data):
        """Simulate handling returned control by providing weather data."""
        invocation_id = return_control_data["invocationId"]
        invocation_inputs = return_control_data["invocationInputs"][0]

        # Simulate weather API response (using function result format)
        weather_response = {
            "actionGroup": invocation_inputs["functionInvocationInput"]["actionGroup"],
            "function": invocation_inputs["functionInvocationInput"]["function"],
            "responseBody": {
                "TEXT": {
                    "body": "It's 55F in Seattle today, rainy."
                }
            }
        }

        # Prepare session state with the returned control results
        session_state = {
            "invocationId": invocation_id,
            "returnControlInvocationResults": [
                {"functionResult": weather_response}
            ]
        }

        return session_state

    def run_demo(self):
        """Run the demo showcasing multiple InvokeAgent features."""
        print("Starting Weather Agent Demo...")

        # Step 1: Initial request for weather
        print("Step 1: Asking for Seattle weather")
        initial_prompt = "What's the weather like in Seattle today?"
        response = self.invoke_agent(initial_prompt)

        if response["type"] == "return_control":
            print("Agent requested weather data via return control.")

            # Step 2: Handle return control and provide weather data
            session_state = self.handle_return_control(response["data"])
            print("Step 2: Providing weather data back to agent.")
            final_response = self.invoke_agent(
                "Process the weather data",
                session_state=session_state,
                end_session=False # Keeping session open for potential follow-up
            )

            if final_response["type"] == "completion":
                print("\nFinal Response:")
                print(final_response["completion"])
                if final_response["trace"]:
                    print("\nTrace Information:")
                    for trace in final_response["trace"]:
                        print(json.dumps(trace, indent=2))
            else:
                # Should not happen if session_state is provided correctly
                logger.warning(f"Unexpected response type after providing session state: {final_response.get('type')}")
                print("Received unexpected response after providing data.")

        elif response["type"] == "completion":
             # Agent answered directly without needing function call/return control
            print("\nAgent responded directly:")
            print(response["completion"])
            if response["trace"]:
                print("\nTrace Information:")
                for trace in response["trace"]:
                    print(json.dumps(trace, indent=2))
        else:
            # Handle other unexpected response types
            logger.error(f"Unexpected initial response type: {response.get('type')}")
            print(f"Received unexpected response type: {response.get('type')}")

if __name__ == "__main__":
    try:
        demo = WeatherAgentDemo()
        demo.run_demo()
    except Exception as e:
        logger.error(f"Demo failed unexpectedly: {e}", exc_info=True) # Add traceback info
