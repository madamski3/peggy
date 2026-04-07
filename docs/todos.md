Bugfixes
- Verify that _sync_calendar reliably creates calendar events for all scheduled todos


Optimizations
- Agent needs a mechanism to decompose todos more intelligently without just defaulting to generic steps ("")
    - What should trigger this? Should it be automatic at the time of Todo creation?
    - Could web search help?
- The agent should be more proactive, like an executive assistant
    - When I tell the agent something I need to do, it should proactively create Todos and schedule them if appropriate
    - Need to give the agent guidance on when todos should be scheduled immediately or saved for later (e.g. Todo in backlog or with further out due date should not immediately be scheduled)
- DraftEmail or other pre-defined functions should have workflows built out
- Need to give the agent a tool (or update existing) to enable it to move a project to backlog



New Features
- Implement prompt caching
    - What decisions need to be made?
- Create a daily process where the LLM automatically reviews the prior day's interactions, notes the information that is worth retaining in long term memory, and stores that information
    - Open question: How should that information be stored? In {date}.md files? Converted to ProfileFacts and vectorized?
    - The goal should be to store it in a way that will be most efficiently accessible and scale well as the agent learns more tidbits about me. One challenge is that the information will be random and can touch all different parts of my life - a new friend I have, foods I do/don't like, college major, childhood memories - which makes it a bit difficult to organize
- Enable multiple user accounts
    - Each user's data and third party connections should be separate and confined to their own environment
    - We will need a simple onboarding flow for new users. If there is an off-the-shelf registration solution from nginx or another third party
- Serve the application publicly (blocked by multiple users work)

General Thoughts
- We need to improve the response time of the system
- Structured outputs should be formatted better instead of just dumping JSON output