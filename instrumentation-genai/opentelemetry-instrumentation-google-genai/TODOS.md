# TODOs

## Fundamentals

Here are some TODO items required to achieve stability for this package:

 - Add more span-level attributes for response information
 - Verify and correct formatting of events:
   - Including the 'role' field for message events
   - Including tool invocation information
 - Emit events for safety ratings when they block responses
 - Additional cleanup/improvement tasks such as:
   - Adoption of 'wrapt' instead of 'functools.wraps'
   - Bolstering test coverage

## Future

Beyond the above TODOs, it would also be desirable to extend the
instrumentation beyond `generate_content` to other API surfaces.