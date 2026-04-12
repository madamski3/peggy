Bugfixes
- Verify that _sync_calendar reliably creates calendar events for all scheduled todos
- Confirm that we are pulling the Primary account in cases where multiple emails/accounts exist


Optimizations
- Extract static configurations and variables to a single global vars file
    - This should include any static values that represent product decisions and/or business logic. This includes model choices (i.e. Sonnet vs Haiku).
        - For example, within a for loop, the "1" in "i+1" would be considered trivial and would not be included in this config. However, "top_k" in our tool-fetching logic is a product decision that should be configurable in this globals file
    - Variables in this file should be available synchronously application-wide
- We should cache the user's timezone as a global variable, so that it can be accessed synchronously via the application, rather than requiring database calls
    - If the user timezone is changed within their Profile, the cached variable must be updated as well
    - This may make sense to implement within the global vars file above
    - Can this pattern be extended to all Profile settings?
- Agent needs a mechanism to decompose todos more intelligently without just defaulting to generic steps ("")
    - What should trigger this? Should it be automatic at the time of Todo creation?
    - Could web search help?
- The agent should be more proactive, like an executive assistant
    - When I tell the agent something I need to do, it should proactively create Todos and schedule them if appropriate
    - Need to give the agent guidance on when todos should be scheduled immediately or saved for later (e.g. Todo in backlog or with further out due date should not immediately be scheduled)
- DraftEmail or other pre-defined functions should have workflows built out
- Need to give the agent a tool (or update existing) to enable it to move a project to backlog


New Features
- Create a daily process where the LLM automatically reviews the prior day's interactions, notes the information that is worth retaining in long term memory, and stores that information
    - It should reference any information collected by the application. In addition, it should reference my Claude and Google chat sessions, search history, and other granular histories/data sources
    - Open question: How should that information be stored? In markdown files? Converted to ProfileFacts and vectorized?
    - The ultimate goal is to build a "wiki" about me that the agent can reference as needed
        - Information must be efficiently accessible and scale well as the agent learns more.
        - One challenge is that the information will be random and can touch all different parts of my life - a new friend I have, foods I do/don't like, college major, childhood memories - so a smart and flexible organization system will be very important
- Implement a calendar tab for me to view my Google cal from within the application
    - FullCalendar
        - https://fullcalendar.io/docs/intro
        - https://fullcalendar.io/docs/google-calendar
- Enable multiple user accounts
    - Each user's data and third party connections should be separate and confined to their own environment
    - Auth flow will likely need to be refactored to support multi-tenant
    - We will need a simple onboarding flow for new users. If there is an off-the-shelf registration solution from nginx or another third party
- Serve the application publicly (blocked by multiple users work)


General Thoughts
- We need to improve the response time of the system
    - Open question: Are database calls adding meaningful latency? Look for optimization opportunities if so; otherwise, ignore for now
- Structured outputs should be formatted better instead of just dumping JSON output
- Does it make sense to implement streaming outputs? Seems like an improvement to the web UI, but I don't know whether that would behave well with voice control