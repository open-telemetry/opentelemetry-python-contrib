# TODOs

## Fundamentals

Here are some TODO items required to achieve stability for this package:

  1. Add support for streaming interfaces
  2. Add support for async interfaces
  3. Add more span-level attributes for request configuration
  4. Add more span-level attributes for response information
  5. Verify and correct formatting of events:
     - Including the 'role' field for message events
     - Including tool invocation information
  6. Emit events for safety ratings when they block responses
  7. Additional cleanup/improvement tasks such as:
     - Adoption of 'wrapt' instead of 'functools.wraps'
     - Bolstering test coverage

## Future

Beyond the above TODOs, it would also be desireable to extend the
instrumentation beyond `generate_content` to other API surfaces.