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
- Implement Weather + Financial features that we previously pushed to post-MVP. See #8 within docs/ai_assistant_architecture.md
    - Integrate weather API (hourly forecast)
    - Integrate Plaid (account sync, transactions, net worth)
    - Build financial tools and schedule daily Plaid sync
    - Wire weather into daily planning (agent can now factor in rain, temperature for outdoor scheduling)
    - Test: "What's the weather this afternoon?" → hourly forecast
    - Test: "How much did we spend on dining this month?" → categorized breakdown


General Thoughts
- We need to improve the response time of the system
    - Open question: Are database calls adding meaningful latency? Look for optimization opportunities if so; otherwise, ignore for now
- Structured outputs should be formatted better instead of just dumping JSON output
- Does it make sense to implement streaming outputs? Seems like an improvement to the web UI, but I don't know whether that would behave well with voice control...