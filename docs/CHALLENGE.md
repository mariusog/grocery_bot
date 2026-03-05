# Grocery Bot Challenge — NM i AI 2026

## Pre-Competition Warm-Up

Get familiar with the platform before the main competition starts (March 19, 2026).

- Sign in at `app.ainm.no` with Google
- Create or join a team
- Pick a difficulty, click Play
- Connect your bot via WebSocket, respond with actions each round
- Best score per map is saved — leaderboard = sum of all 4 maps

### MCP Server

```sh
claude mcp add --transport http grocery-bot https://mcp-docs.ainm.no/mcp
```

### Rate Limits

- 40 games per hour
- 300 games per day
- 60-second cooldown between games

---

## Our Best Scores

| Level  | Grid   | Bots | Best Score |
|--------|--------|------|------------|
| Easy   | 12x10  | 1    | 118 pts    |
| Medium | 16x12  | 3    | 35 pts     |
| Hard   | 22x14  | 5    | No score   |
| Expert | 28x18  | 10   | No score   |

---

## Game Mechanics

### Flow

```
Server sends game_state (round N)
  -> Your bot returns actions for each bot
  -> Game state updates, next round begins
  -> Repeat for up to 300 rounds (120s wall-clock limit)
```

### Difficulty Levels

| Level  | Grid   | Bots | Aisles | Item Types | Order Size |
|--------|--------|------|--------|------------|------------|
| Easy   | 12x10  | 1    | 2      | 4          | 3-4        |
| Medium | 16x12  | 3    | 3      | 8          | 3-5        |
| Hard   | 22x14  | 5    | 4      | 12         | 3-5        |
| Expert | 28x18  | 10   | 5      | 16         | 4-6        |

One map per difficulty. Item placement and orders change daily — same day, same game (deterministic).

### Coordinate System

- Origin `(0, 0)` is top-left
- X increases to the right
- Y increases downward

### Scoring

| Event           | Points   |
|-----------------|----------|
| Item delivered  | +1       |
| Order completed | +5 bonus |

### Constraints

- **300 rounds** maximum per game
- **120 seconds** wall-clock limit
- **3 items** per bot inventory
- **Collision** — bots block each other (no two on same tile, except spawn)
- **Full visibility** — entire map visible every round
- **2-second timeout** per round for response
- **Disconnect = game over** — no reconnect

---

## Orders

Orders are sequential and infinite (rounds are the only limit):

- **Active order** — current order, you can deliver items for it
- **Preview order** — next order, visible but cannot deliver yet (can pre-pick items)
- When an order completes, a new one appears

### Delivery Cascade

When an order completes at drop-off, the next order activates and remaining inventory items are **re-checked** against the new active order. Items matching the new order are delivered immediately.

---

## WebSocket Protocol

### Connection

```
wss://game.ainm.no/ws?token=<jwt_token>
```

Get a token by clicking "Play" on a map at `app.ainm.no/challenge`.

### Game State Message (server -> bot)

```json
{
  "type": "game_state",
  "round": 42,
  "max_rounds": 300,
  "grid": {
    "width": 16,
    "height": 12,
    "walls": [[1,1], [1,2], [3,1]]
  },
  "bots": [
    {"id": 0, "position": [3, 7], "inventory": ["milk"]},
    {"id": 1, "position": [5, 3], "inventory": []},
    {"id": 2, "position": [10, 7], "inventory": ["bread", "eggs"]}
  ],
  "items": [
    {"id": "item_0", "type": "milk", "position": [2, 1]},
    {"id": "item_1", "type": "bread", "position": [4, 1]}
  ],
  "orders": [
    {
      "id": "order_0",
      "items_required": ["milk", "bread", "eggs"],
      "items_delivered": ["milk"],
      "complete": false,
      "status": "active"
    },
    {
      "id": "order_1",
      "items_required": ["cheese", "butter"],
      "items_delivered": [],
      "complete": false,
      "status": "preview"
    }
  ],
  "drop_off": [1, 10],
  "score": 12
}
```

### Field Reference

| Field         | Type     | Description                                      |
|---------------|----------|--------------------------------------------------|
| `round`       | int      | Current round (0-indexed)                        |
| `max_rounds`  | int      | Maximum rounds (300)                             |
| `grid.walls`  | int[][]  | List of [x, y] wall positions                    |
| `bots`        | object[] | All bots with id, position [x,y], and inventory  |
| `items`       | object[] | All items on shelves with id, type, position [x,y]|
| `orders`      | object[] | Active + preview orders (max 2 visible)          |
| `drop_off`    | int[]    | [x, y] of the drop-off zone                     |
| `score`       | int      | Current score                                    |

### Bot Response (bot -> server)

Send within 2 seconds:

```json
{
  "actions": [
    {"bot": 0, "action": "move_up"},
    {"bot": 1, "action": "pick_up", "item_id": "item_3"},
    {"bot": 2, "action": "drop_off"}
  ]
}
```

### Actions

| Action       | Extra Fields | Description                         |
|--------------|-------------|-------------------------------------|
| `move_up`    | —           | Move one cell up (y-1)              |
| `move_down`  | —           | Move one cell down (y+1)            |
| `move_left`  | —           | Move one cell left (x-1)            |
| `move_right` | —           | Move one cell right (x+1)           |
| `pick_up`    | `item_id`   | Pick up item from adjacent shelf    |
| `drop_off`   | —           | Deliver matching items at drop-off  |
| `wait`       | —           | Do nothing                          |

Invalid actions are treated as `wait`.

### Pickup Rules

- Bot must be **adjacent** (Manhattan distance 1) to the shelf with the item
- Bot inventory must not be full (max 3 items)
- `item_id` must match an item currently on the map

### Dropoff Rules

- Bot must be standing **on** the drop-off cell
- Only items matching the **active order** are delivered
- Non-matching items stay in inventory
- When an order completes, the next order activates and remaining items are re-checked (cascade)

---

## Example Bot

```python
import asyncio
import json
import websockets

WS_URL = "wss://game.ainm.no/ws?token=YOUR_TOKEN"

async def play():
    async with websockets.connect(WS_URL) as ws:
        while True:
            msg = json.loads(await ws.recv())

            if msg["type"] == "game_over":
                print(f"Game over! Score: {msg['score']}")
                break

            state = msg
            actions = []

            for bot in state["bots"]:
                action = decide(bot, state)
                actions.append(action)

            await ws.send(json.dumps({"actions": actions}))

def decide(bot, state):
    x, y = bot["position"]
    drop_off = state["drop_off"]

    if bot["inventory"] and [x, y] == drop_off:
        return {"bot": bot["id"], "action": "drop_off"}

    if len(bot["inventory"]) >= 3:
        return move_toward(bot["id"], x, y, drop_off)

    active = next((o for o in state["orders"] if o["status"] == "active"), None)
    if not active:
        return {"bot": bot["id"], "action": "wait"}

    needed = list(active["items_required"])
    for d in active["items_delivered"]:
        if d in needed:
            needed.remove(d)

    for item in state["items"]:
        if item["type"] in needed:
            ix, iy = item["position"]
            if abs(ix - x) + abs(iy - y) == 1:
                return {"bot": bot["id"], "action": "pick_up", "item_id": item["id"]}

    for item in state["items"]:
        if item["type"] in needed:
            return move_toward(bot["id"], x, y, item["position"])

    if bot["inventory"]:
        return move_toward(bot["id"], x, y, drop_off)

    return {"bot": bot["id"], "action": "wait"}

def move_toward(bot_id, x, y, target):
    tx, ty = target
    if abs(tx - x) > abs(ty - y):
        return {"bot": bot_id, "action": "move_right" if tx > x else "move_left"}
    elif ty != y:
        return {"bot": bot_id, "action": "move_down" if ty > y else "move_up"}
    return {"bot": bot_id, "action": "wait"}

asyncio.run(play())
```

---

## Game Over Message

```json
{
  "type": "game_over",
  "score": 96,
  "rounds_used": 300,
  "items_delivered": 41,
  "orders_completed": 11
}
```

---

## Key Strategic Insights

- **+5 order bonus is ~60% of score** — completing orders matters more than raw item delivery
- **Deterministic per day** — same day = same game, so you can observe and optimize
- **Preview pipelining** — pre-pick items for the next order while finishing the current one
- **Cascade delivery** — items for the next order already in inventory auto-deliver on order transition
- **Inventory limit of 3** — plan trips to maximize items per delivery run
- **Bots block each other** — collision avoidance is critical on Hard/Expert
- **Items restock** — picked items are replaced on the same shelf (infinite supply)
