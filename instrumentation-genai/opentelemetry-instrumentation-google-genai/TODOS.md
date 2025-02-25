# TODOs

## Fundamentals

Here are some TODO items required to achieve stability for this package:

  1. Add more span-level attributes for request configuration
  2. Add more span-level attributes for response information
  3. Verify and correct formatting of events:
     - Including the 'role' field for message events
     - Including tool invocation information
  4. Emit events for safety ratings when they block responses
  5. Additional cleanup/improvement tasks such as:
     - Adoption of 'wrapt' instead of 'functools.wraps'
     - Bolstering test coverage
  6. Migrate tests to use VCR.py

## Future

Beyond the above TODOs, it would also be desirable to extend the
instrumentation beyond `generate_content` to other API surfaces.