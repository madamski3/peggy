Fix timezone issues
- Timezones appear to be used and applied inconsistently across the application. Different objects stored at the same time are being written with created_at 7 hours different from each other
- We need to centralize timestamp/timezone logic within the codebase, so that all components know the correct current time
- The user's local timezone should dictate the timezone that is presented in the web UI

Add tools to the User Interface
- On the Todos and Tasks tabs of the web UI, add edit functionality that allows me to manually update the status of individual Todos and Tasks
- I would also like a delete button that allows me to delete the Todo/Task from the database entirely

Improve response time of the system

Need to build a system to close completed Todos and Tasks
- Right now, the only way to close the loop on a completed Todo is for me expressly tell the agent. I need a system that pulls updates from me (maybe even infers them proactively), rather than depending on me
- Every morning, we should present the user with a brief overview of the prior day's Tasks, with an option on each Task to indicate whether that Task needs to be rescheduled. Beside each Task, add a text input section for optional notes
- Once the user submits the form, the agent should mark the Tasks that were NOT rescheduled as complete. It should also complete the Todo if appropriate.
- The agent should then reschedule the tasks from the prior day that the user indicated needed to be
- Eventually, we can get smarter and assume that some Tasks/Todos can be auto-closed, and other optimizations
