# Solstice Agent Demo Pack

This demo pack is optimized for one thing: making Sol feel real immediately.

Do not explain the architecture first. Show the magic first.

## Canonical Demo: The Agent On Your Machine (90 seconds)

Goal: prove that Sol is not just another chatbot wrapper.

Script:
1. Install or open `solstice-agent`
2. Prompt: `Summarize this repo and tell me how it works.`
3. Prompt: `Find the file that defines the security rules.`
4. Prompt: `Create demo_notes.txt with the key takeaways.`

What the audience should feel:
- it can see the machine
- it can reason over local files
- it can take action
- it did not need a web app or cloud dashboard to matter

## Demo 2: Tool Use + Safety (2 minutes)

Goal: show that the agent is useful and constrained.

Script:
1. Prompt: `Run "git status".`
2. Prompt: `List the files in this directory.`
3. Prompt: `Try to delete a folder named temp-test.`

Expected outcome:
- safe commands run
- destructive action is blocked or requires confirmation

## Demo 3: Browser + Web (2 minutes)

Goal: show that Sol can leave the local machine when asked.

Script:
1. Prompt: `Search for "open source AI agent local first" and summarize the top results.`
2. Prompt: `Open the strongest result and extract the main claims.`

Expected outcome:
- uses web tools
- reads real pages
- returns grounded output

## Demo 4: API Blackbox (2 minutes)

Goal: show the strongest technical wedge.

Script:
1. Prompt: `Inspect https://api.example.com and tell me what endpoints exist.`
2. Prompt: `Guess the auth pattern and summarize the API shape.`

Expected outcome:
- invokes the API discovery path
- makes Sol feel unusually capable

## Demo 5: Memory (60 seconds)

Goal: show persistence in a way normal people instantly understand.

Script:
1. Prompt: `Remember that I deploy production on Fridays.`
2. Restart or open a fresh session.
3. Prompt: `When do I deploy production?`

Expected outcome:
- shows continuity
- turns Sol from a toy into “my agent”

## Demo 6: Same Brain Everywhere (2 minutes)

Goal: show the cross-channel story without over-explaining it.

Script:
1. Ask Sol something locally.
2. Message the connected Telegram or Discord bot.
3. Ask a follow-up that depends on previous context.

Expected outcome:
- same memory
- same personality
- same agent across surfaces

## How To Present It

Lead with:

`This is an open-source AI agent that lives on your computer.`

Then show:

- one prompt
- one visible action
- one useful result

Avoid:

- long architecture explanations
- tool counts
- channel counts
- benchmark slides before the demo

## Best Short Clips To Record

- install -> first useful action
- repo summary -> file creation
- dangerous command -> confirmation gate
- wake word -> spoken response
- local session -> Telegram follow-up

## Demo Rule

If the demo cannot be understood with the sound off in 15 seconds, it is too long.
