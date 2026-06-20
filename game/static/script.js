document.addEventListener('DOMContentLoaded', () => {
    const API_BASE_URL = ''; 
    let humanPlayerId = "P1";
    let opponentPlayerId = "P2";

    // UI Elements
    const opponentIdElem = document.getElementById('opponent-id');
    const opponentHpElem = document.getElementById('opponent-hp');
    const opponentDeckCountElem = document.getElementById('opponent-deck-count');
    const opponentHandCountElem = document.getElementById('opponent-hand-count');
    const opponentGraveyardCountElem = document.getElementById('opponent-graveyard-count');
    const opponentFieldElem = document.getElementById('opponent-field');
    const opponentMaxFieldElem = document.getElementById('opponent-max-field');
    const opponentCurrentFieldElem = document.getElementById('opponent-current-field');

    const playerIdElem = document.getElementById('player-id');
    const playerHpElem = document.getElementById('player-hp');
    const playerDeckCountElem = document.getElementById('player-deck-count');
    const playerHandCountElem = document.getElementById('player-hand-count');
    const playerGraveyardCountElem = document.getElementById('player-graveyard-count');
    const playerFieldElem = document.getElementById('player-field');
    const playerMaxFieldElem = document.getElementById('player-max-field');
    const playerCurrentFieldElem = document.getElementById('player-current-field');
    const playerHandElem = document.getElementById('player-hand');

    const roundNumberElem = document.getElementById('round-number');
    const gameStatusMessageElem = document.getElementById('game-status-message');
    const submitActionsButton = document.getElementById('submit-actions-button');
    const clearActionsButton = document.getElementById('clear-actions-button');

    // Game State & Client-side Action Planning
    let currentGameState = null;
    let playerActions = []; // {type: 'PLAY_CARD', card_instance_id: str, card_data: obj} OR 
                           // {type: 'ATTACK', attacker_instance_id: str, target_instance_id: str, attacker_name: str, target_name: str}
    let selectedAttackerCardId = null;
    let lastRenderedActionLogCount = 0; // To track new logs for animation

    // --- Helper Functions ---
    // Attribute icons are loaded from the shared map (shared/attribute_icons.json,
    // synced into static/). Keyed by lowercase attribute id -> {symbol,name,blurb}.
    let ATTR_ICONS = {};

    const PARTY_COLOURS = {
        "Labour": "#D82A20", "National": "#00529F", "Green": "#098137",
        "Greens": "#098137", "ACT": "#F5C400", "NZ First": "#1a1a1a",
        "Opportunity": "#0a9c96", "TOP": "#0a9c96"
    };
    function partyColour(party) {
        if (PARTY_COLOURS[party]) return PARTY_COLOURS[party];
        let h = 0;
        for (const ch of (party || "")) h = (h * 31 + ch.charCodeAt(0)) % 360;
        return `hsl(${h}, 45%, 38%)`;   // deterministic colour for fictional parties
    }
    function initials(name) {
        return (name || "?").split(/\s+/).map(w => w[0] || "").join("").slice(0, 2).toUpperCase();
    }
    function tierClass(v) {
        return v < 40 ? "low" : (v < 70 ? "mid" : "high");
    }

    async function loadIconsAndLegend() {
        try {
            const raw = await (await fetch('/static/attribute_icons.json')).json();
            const legend = document.getElementById('legend');
            for (const [key, meta] of Object.entries(raw)) {
                if (key.startsWith('_')) continue;
                ATTR_ICONS[key.toLowerCase()] = meta;
                if (meta.name) ATTR_ICONS[meta.name.toLowerCase()] = meta;
                if (meta.site_id) ATTR_ICONS[meta.site_id.toLowerCase()] = meta;
                if (legend) {
                    const li = document.createElement('li');
                    li.innerHTML = `<span class="sc-icon">${meta.svg || meta.symbol}</span>` +
                        `<span><b>${meta.name}</b> — <span class="blurb">${meta.blurb || ''}</span></span>`;
                    legend.appendChild(li);
                }
            }
        } catch (e) {
            console.warn('Could not load attribute icons:', e);
        }
    }

    function createCardElement(cardData, locationType) {
        const cardDiv = document.createElement('div');
        cardDiv.classList.add('card', 'sc-card');
        cardDiv.dataset.instanceId = cardData.instance_id;
        cardDiv.dataset.name = cardData.name; // For identification in events/logs
        cardDiv.style.setProperty('--party', partyColour(cardData.party));
        // Rarity is computed server-side over the whole deck (geometric mean +
        // exponential buckets) and drives the banner colour.
        cardDiv.style.setProperty('--rarity', cardData.rarity || '#4b5563');

        if (locationType === 'hand') {
            cardDiv.classList.add('hand-card');
            cardDiv.draggable = true;
        } else if (locationType === 'player-field') {
            cardDiv.classList.add('field-card', 'player-card');
        } else if (locationType === 'opponent-field') {
            cardDiv.classList.add('field-card', 'opponent-card');
        }

        const statsHtml = Object.entries(cardData.attributes).map(([key, value]) => {
            const meta = ATTR_ICONS[key.toLowerCase()] || {};
            const sym = meta.svg || meta.symbol || '•';
            const name = meta.name || key;
            return `<div class="sc-stat" title="${name}: ${value}">` +
                   `<span class="sc-icon">${sym}</span>` +
                   `<span class="sc-val ${tierClass(value)}">${value}</span></div>`;
        }).join('');

        cardDiv.innerHTML = `
            <div class="sc-banner">
                <h3 class="sc-name">${cardData.name}</h3>
                <span class="sc-party">${cardData.party}</span>
                <span class="sc-portrait sc-initials">${initials(cardData.name)}</span>
            </div>
            <div class="sc-hp">HP: ${cardData.current_hp}/${cardData.max_hp}</div>
            <div class="sc-stats">${statsHtml}</div>
            <div class="attack-target-indicator" style="display: none;"></div>
        `;
        return cardDiv;
    }
    
    function updateCardAttackIndicator(cardElement, targetName) {
        const indicator = cardElement.querySelector('.attack-target-indicator');
        if (indicator) {
            if (targetName) {
                indicator.textContent = `Attacks: ${targetName.substring(0,10)}...`;
                indicator.style.display = 'block';
                cardElement.classList.add('has-attack-planned');
            } else {
                indicator.textContent = '';
                indicator.style.display = 'none';
                cardElement.classList.remove('has-attack-planned');
            }
        }
    }

    // --- Optimistic UI Updates & Action Management ---
    function addPlayCardAction(cardInstanceId, cardData) {
        // Prevent duplicate play actions for the same card
        if (playerActions.some(action => action.type === 'PLAY_CARD' && action.card_instance_id === cardInstanceId)) {
            return false;
        }
        playerActions.push({ type: 'PLAY_CARD', card_instance_id: cardInstanceId, card_data: cardData });
        
        // Optimistic UI: Move card from hand to field
        const cardElement = playerHandElem.querySelector(`.card[data-instance-id="${cardInstanceId}"]`);
        if (cardElement) {
            playerFieldElem.appendChild(cardElement);
            cardElement.classList.remove('hand-card');
            cardElement.classList.add('field-card', 'player-card');
            cardElement.draggable = false; // No longer draggable from field
            // Re-bind click listener for field card behavior
            cardElement.removeEventListener('dragstart', handleDragStart); // if it had one
            cardElement.addEventListener('click', handlePlayerFieldCardClick);
        }
        updatePlayerStatsUI(); // Reflect change in hand/field counts
        return true;
    }

    function addAttackAction(attackerId, targetId, targetNameOverride) {
        // Prevent multiple attacks from the same attacker
        if (playerActions.some(action => action.type === 'ATTACK' && action.attacker_instance_id === attackerId)) {
            alert("This card already has a planned attack.");
            return false;
        }
        const attackerCardElem = playerFieldElem.querySelector(`.card[data-instance-id="${attackerId}"]`);
        if (!attackerCardElem) return false;

        // targetNameOverride is supplied for base attacks (targetId is a player id,
        // so there is no card element to look up).
        let targetName = targetNameOverride;
        if (!targetName) {
            const targetCardElem = opponentFieldElem.querySelector(`.card[data-instance-id="${targetId}"]`);
            if (!targetCardElem) return false;
            targetName = targetCardElem.dataset.name;
        }

        playerActions.push({
            type: 'ATTACK',
            attacker_instance_id: attackerId,
            target_instance_id: targetId,
            attacker_name: attackerCardElem.dataset.name,
            target_name: targetName
        });
        updateCardAttackIndicator(attackerCardElem, targetName);
        return true;
    }

    function clearPlannedActions() {
        // Re-render from currentGameState to reset optimistic changes
        // This is simpler than trying to undo each action individually
        playerActions = [];
        selectedAttackerCardId = null;
        renderGameState(currentGameState, false); // false to skip animations
        gameStatusMessageElem.textContent = "Planned actions cleared. Make your move.";
    }
    clearActionsButton.addEventListener('click', clearPlannedActions);


    // --- Rendering Game State ---
    function renderGameState(state, animate = true) {
        const oldGameState = currentGameState;
        currentGameState = state;

        if (!state || !state.players) {
            console.error("Invalid game state received:", state);
            gameStatusMessageElem.textContent = "Error: Invalid game data from server.";
            return;
        }

        humanPlayerId = game_logic_config.PLAYER_IDS[0]; // From backend config
        opponentPlayerId = game_logic_config.PLAYER_IDS[1];

        const playerState = state.players[humanPlayerId];
        const opponentState = state.players[opponentPlayerId];

        if (!playerState || !opponentState) {
            console.error("Player or opponent state missing:", state);
            gameStatusMessageElem.textContent = "Error: Player data missing.";
            return;
        }
        
        // Update Player UI (stats are always from server truth)
        updatePlayerStatsUI();
        updateOpponentStatsUI();

        // Render Player Hand (always from server truth)
        playerHandElem.innerHTML = '';
        playerState.hand.forEach(card => {
            const cardElem = createCardElement(card, 'hand');
            cardElem.addEventListener('dragstart', handleDragStart);
            cardElem.addEventListener('dragend', handleDragEnd);
            playerHandElem.appendChild(cardElem);
        });

        // Render Player Field (server truth)
        playerFieldElem.innerHTML = '';
        playerState.field.forEach(card => {
            const cardElem = createCardElement(card, 'player-field');
            cardElem.addEventListener('click', handlePlayerFieldCardClick);
            playerFieldElem.appendChild(cardElem);
        });
        
        // Render Opponent Field (server truth)
        opponentFieldElem.innerHTML = '';
        opponentState.field.forEach(card => {
            const cardElem = createCardElement(card, 'opponent-field');
            cardElem.addEventListener('click', handleOpponentFieldCardClick);
            opponentFieldElem.appendChild(cardElem);
        });

        // Apply optimistic UI for actions planned but not yet submitted
        // This ensures that if renderGameState is called mid-turn (e.g. after clearing actions),
        // the optimistically played cards are re-added to field, and attack indicators are re-shown.
        const tempActions = [...playerActions]; // Operate on a copy
        playerActions = []; // Clear and re-add to re-trigger optimistic UI logic
        tempActions.forEach(action => {
            if (action.type === 'PLAY_CARD') {
                addPlayCardAction(action.card_instance_id, action.card_data);
            } else if (action.type === 'ATTACK') {
                addAttackAction(action.attacker_instance_id, action.target_instance_id);
                 // Re-apply attack indicator if card still on field
                const attackerElem = playerFieldElem.querySelector(`.card[data-instance-id="${action.attacker_instance_id}"]`);
                if (attackerElem) {
                    updateCardAttackIndicator(attackerElem, action.target_name);
                }
            }
        });


        roundNumberElem.textContent = state.round_number;

        if (state.game_phase === "GAME_OVER") {
            gameStatusMessageElem.textContent = `Game Over! Winner: ${state.winner}`;
            submitActionsButton.disabled = true;
            clearActionsButton.disabled = true;
        } else {
            gameStatusMessageElem.textContent = `Round ${state.round_number} - Your turn.`;
            submitActionsButton.disabled = false;
            clearActionsButton.disabled = false;
        }
        
        // Resolution is replayed from structured `state.events` by replayEvents(),
        // invoked explicitly after a turn submission (see submitPlayerActionsToServer).
        clearSelectionUI(); // Clear attacker selection visuals
    }

    function updatePlayerStatsUI() {
        if (!currentGameState || !currentGameState.players[humanPlayerId]) return;
        const playerState = currentGameState.players[humanPlayerId];
        
        playerIdElem.textContent = playerState.id;
        playerHpElem.textContent = playerState.health_points;
        playerDeckCountElem.textContent = playerState.deck.length;
        playerGraveyardCountElem.textContent = playerState.graveyard.length;
        playerMaxFieldElem.textContent = playerState.max_cards_on_field;
        
        // Hand and field counts consider optimistic plays
        const optimisticallyPlayedCards = playerActions.filter(a => a.type === 'PLAY_CARD').length;
        playerHandCountElem.textContent = playerState.hand.length - optimisticallyPlayedCards;
        playerCurrentFieldElem.textContent = playerState.field.length + optimisticallyPlayedCards;
    }

    function updateOpponentStatsUI() {
        if (!currentGameState || !currentGameState.players[opponentPlayerId]) return;
        const opponentState = currentGameState.players[opponentPlayerId];

        opponentIdElem.textContent = opponentState.id;
        opponentHpElem.textContent = opponentState.health_points;
        opponentDeckCountElem.textContent = opponentState.deck.length;
        opponentHandCountElem.textContent = opponentState.hand.length;
        opponentGraveyardCountElem.textContent = opponentState.graveyard.length;
        opponentMaxFieldElem.textContent = opponentState.max_cards_on_field;
        opponentCurrentFieldElem.textContent = opponentState.field.length;
    }


    // --- Structured resolution replay --------------------------------------
    // The server returns `state.events`: an ordered list of structured events for
    // the round just resolved. We narrate them one at a time and highlight the
    // cards/bases involved, instead of parsing log strings.
    function findCardEls(ids) {
        return (ids || [])
            .map(id => id && document.querySelector(`.card[data-instance-id="${id}"]`))
            .filter(Boolean);
    }

    function flashEl(el, cls, ms = 600) {
        if (!el) return;
        el.classList.add(cls);
        setTimeout(() => el.classList.remove(cls), ms);
    }

    function describeEvent(ev) {
        switch (ev.type) {
            case 'round_start':
                return { cls: 'ev-round', text: `— Round ${ev.round} —` };
            case 'attack_order': {
                const names = (ev.order || []).map(o => `${o.name} (Div ${o.divination})`).join('  →  ');
                return { cls: 'ev-order', text: `Order (Divination decides): ${names || '— no attacks —'}` };
            }
            case 'play':
                return { cls: 'ev-play', text: `▶ ${ev.player} plays ${ev.card}`, ids: [ev.instance_id] };
            case 'attack': {
                const tgt = ev.target.kind === 'base' ? `${ev.target.player}'s BASE` : ev.target.name;
                return {
                    cls: 'ev-attack', text: `⚔ ${ev.attacker.name} attacks ${tgt}`,
                    ids: [ev.attacker.instance_id, ev.target.instance_id],
                    base: ev.target.kind === 'base' ? ev.target.player : null
                };
            }
            case 'retarget':
                return { cls: 'ev-retarget', text: `↪ Authenticity: redirected from ${ev.from_name} to ${ev.target.name}`, ids: [ev.target.instance_id] };
            case 'miss':
                return { cls: 'ev-miss', text: `✗ ${ev.attacker.name} MISSED (Specificity)`, ids: [ev.attacker.instance_id] };
            case 'fizzle':
                return { cls: 'ev-miss', text: `· ${ev.attacker.name}'s attack fizzles`, ids: [ev.attacker.instance_id] };
            case 'damage':
                return { cls: 'ev-damage', text: `💥 ${ev.target.name} takes ${ev.amount} (HP ${ev.current_hp}/${ev.max_hp})`, ids: [ev.target.instance_id], flash: 'damage-flash' };
            case 'reflect':
                return { cls: 'ev-reflect', text: `↩ Forthrightness: ${ev.source.name} reflects ${ev.amount} onto ${ev.target.name} (HP ${ev.current_hp}/${ev.max_hp})`, ids: [ev.target.instance_id], flash: 'reflect-flash' };
            case 'civility':
                return { cls: 'ev-civility', text: `☠ Civility pierce: ${ev.attacker.name} → ${ev.amount} to ${ev.target_player} (HP ${ev.player_hp})`, base: ev.target_player };
            case 'base_attack':
                return { cls: 'ev-base', text: `🏛 ${ev.attacker.name} hits ${ev.target_player}'s base for ${ev.amount} (HP ${ev.player_hp})`, ids: [ev.attacker.instance_id], base: ev.target_player };
            case 'defeat':
                return { cls: 'ev-defeat', text: `✟ ${ev.card.name} is defeated`, ids: [ev.card.instance_id], flash: 'defeated-animation' };
            case 'game_over':
                return { cls: 'ev-gameover', text: `🏆 Game Over — Winner: ${ev.winner}` };
            default:
                return null;
        }
    }

    function delayForEvent(type) {
        if (type === 'attack_order') return 900;
        if (['damage', 'reflect', 'base_attack', 'defeat'].includes(type)) return 750;
        if (type === 'attack') return 550;
        return 400;
    }

    async function replayEvents(events) {
        const panel = document.getElementById('resolution-panel');
        const logOl = document.getElementById('resolution-log');
        logOl.innerHTML = '';
        panel.style.display = 'block';
        submitActionsButton.disabled = true;
        clearActionsButton.disabled = true;
        gameStatusMessageElem.textContent = "Resolving…";

        for (const ev of (events || [])) {
            const d = describeEvent(ev);
            if (!d) continue;

            const li = document.createElement('li');
            li.className = d.cls;
            li.textContent = d.text;
            logOl.appendChild(li);
            logOl.scrollTop = logOl.scrollHeight;

            const els = findCardEls(d.ids);
            els.forEach(el => el.classList.add('event-focus'));
            if (d.flash) els.forEach(el => flashEl(el, d.flash));
            if (d.base) {
                const baseEl = (d.base === opponentPlayerId)
                    ? document.getElementById('opponent-base')
                    : document.getElementById('human-player-area');
                flashEl(baseEl, 'base-hit', 700);
            }

            await new Promise(r => setTimeout(r, delayForEvent(ev.type)));
            els.forEach(el => el.classList.remove('event-focus'));
        }

        if (currentGameState.game_phase === "GAME_OVER") {
            gameStatusMessageElem.textContent = `Game Over! Winner: ${currentGameState.winner}`;
        } else {
            gameStatusMessageElem.textContent = `Round ${currentGameState.round_number} - Your turn.`;
            submitActionsButton.disabled = false;
            clearActionsButton.disabled = false;
        }
    }


    // --- Event Handlers ---
    let draggedCardData = null; // Store data of the card being dragged

    function handleDragStart(event) {
        const cardInstanceId = event.target.dataset.instanceId;
        // Find card data from player's hand in currentGameState
        const playerState = currentGameState.players[humanPlayerId];
        const cardData = playerState.hand.find(c => c.instance_id === cardInstanceId);
        
        if (cardData) {
            draggedCardData = cardData; // Store the full card object
            event.dataTransfer.setData('text/plain', cardInstanceId);
            event.target.classList.add('dragging');
        } else {
            event.preventDefault(); // Should not happen if UI is synced
        }
    }

    function handleDragEnd(event) {
        event.target.classList.remove('dragging');
        draggedCardData = null;
    }

    playerFieldElem.addEventListener('dragover', (event) => {
        event.preventDefault(); 
        playerFieldElem.classList.add('drag-over');
    });

    playerFieldElem.addEventListener('dragleave', () => {
        playerFieldElem.classList.remove('drag-over');
    });

    playerFieldElem.addEventListener('drop', (event) => {
        event.preventDefault();
        playerFieldElem.classList.remove('drag-over');
        const cardInstanceId = event.dataTransfer.getData('text/plain');
        
        if (draggedCardData && draggedCardData.instance_id === cardInstanceId) {
            const playerState = currentGameState.players[humanPlayerId];
            const optimisticallyPlayedCardsCount = playerActions.filter(a => a.type === 'PLAY_CARD').length;
            if (playerState.field.length + optimisticallyPlayedCardsCount >= playerState.max_cards_on_field) {
                alert("Cannot play more cards, field is full or will be full with planned plays!");
                return;
            }
            if (addPlayCardAction(cardInstanceId, draggedCardData)) {
                 gameStatusMessageElem.textContent = `Card ${draggedCardData.name} planned to play.`;
            }
        }
        draggedCardData = null; // Clear after drop
    });

    function clearSelectionUI() {
        if (selectedAttackerCardId) {
            const prevSelected = playerFieldElem.querySelector(`.card[data-instance-id="${selectedAttackerCardId}"]`);
            if (prevSelected) prevSelected.classList.remove('selected-attacker');
        }
        selectedAttackerCardId = null;
    }

    function handlePlayerFieldCardClick(event) {
        const clickedCard = event.target.closest('.card.player-card');
        if (!clickedCard) return;
        const cardInstanceId = clickedCard.dataset.instanceId;

        // If this card already has an attack planned, clicking it again could perhaps cancel that specific attack.
        // For now, let's keep it simple: selecting an attacker.
        const existingAttack = playerActions.find(a => a.type === 'ATTACK' && a.attacker_instance_id === cardInstanceId);
        if (existingAttack) {
            if (confirm(`Card ${clickedCard.dataset.name} is already targeting ${existingAttack.target_name}. Remove this attack?`)) {
                playerActions = playerActions.filter(a => !(a.type === 'ATTACK' && a.attacker_instance_id === cardInstanceId));
                updateCardAttackIndicator(clickedCard, null);
                clearSelectionUI(); // Clear general selection too
            }
            return;
        }

        clearSelectionUI(); // Deselect any previously selected attacker
        clickedCard.classList.add('selected-attacker');
        selectedAttackerCardId = cardInstanceId;
        gameStatusMessageElem.textContent = `Selected ${clickedCard.dataset.name} to attack. Click an opponent's card on field to target.`;
    }

    function handleOpponentFieldCardClick(event) {
        const targetCard = event.target.closest('.card.opponent-card');
        if (!targetCard) return;

        if (!selectedAttackerCardId) {
            alert("Select one of your cards on the field to be an attacker first!");
            return;
        }

        const targetInstanceId = targetCard.dataset.instanceId;
        if (addAttackAction(selectedAttackerCardId, targetInstanceId)) {
            const attackerElem = playerFieldElem.querySelector(`.card[data-instance-id="${selectedAttackerCardId}"]`);
            gameStatusMessageElem.textContent = `Planned attack: ${attackerElem.dataset.name} -> ${targetCard.dataset.name}.`;
        }
        clearSelectionUI(); // Clear attacker selection after planning an attack
    }

    // Attack the opponent's base directly (their HP). Useful when they have no
    // cards on the field — select your attacker, then click the opponent base.
    const opponentBaseElem = document.getElementById('opponent-base');
    if (opponentBaseElem) {
        opponentBaseElem.addEventListener('click', () => {
            if (!selectedAttackerCardId) {
                alert("Select one of your cards first, then click the opponent's base to attack it directly.");
                return;
            }
            if (addAttackAction(selectedAttackerCardId, opponentPlayerId, "BASE")) {
                gameStatusMessageElem.textContent = `Planned attack on ${opponentPlayerId}'s base.`;
            }
            clearSelectionUI();
        });
    }

    async function submitPlayerActionsToServer() {
        if (!currentGameState || currentGameState.game_phase === "GAME_OVER") {
            console.log("Game is over or not started.");
            return;
        }
        // Filter out card_data from PLAY_CARD actions before sending to server
        const actionsForServer = playerActions.map(action => {
            if (action.type === 'PLAY_CARD') {
                return { type: 'PLAY_CARD', player_id: humanPlayerId, card_instance_id: action.card_instance_id };
            }
            if (action.type === 'ATTACK') {
                 return { type: 'ATTACK', player_id: humanPlayerId, attacker_instance_id: action.attacker_instance_id, target_instance_id: action.target_instance_id };
            }
            return action; // Should not happen
        }).filter(Boolean);


        if (actionsForServer.length === 0) {
            if (!confirm("No actions planned. End turn anyway?")) {
                return;
            }
        }

        submitActionsButton.disabled = true;
        clearActionsButton.disabled = true;
        gameStatusMessageElem.textContent = "Submitting actions and ending turn...";

        try {
            const response = await fetch(`${API_BASE_URL}/api/submit_round_actions`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ actions: actionsForServer })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Server error: ${response.status}`);
            }
            const newGameState = await response.json();
            playerActions = []; // Clear client-side planned actions
            // Sync the board to server truth, then narrate the round's structured events.
            renderGameState(newGameState, false);
            await replayEvents(newGameState.events);
        } catch (error) {
            console.error('Error submitting actions:', error);
            gameStatusMessageElem.textContent = `Error: ${error.message}`;
            // Re-enable buttons on error, but state might be inconsistent
            submitActionsButton.disabled = false; 
            clearActionsButton.disabled = false;
        }
    }
    submitActionsButton.addEventListener('click', submitPlayerActionsToServer);

    // --- Initialize Game ---
    async function initGame() {
        submitActionsButton.disabled = true;
        clearActionsButton.disabled = true;
        gameStatusMessageElem.textContent = "Loading game...";
        await loadIconsAndLegend();   // populate ATTR_ICONS + legend before rendering cards
        try {
            const response = await fetch(`${API_BASE_URL}/api/start_game`);
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.error || `Server error: ${response.status}`);
            }
            const initialState = await response.json();
            // Player IDs are now taken from game_logic_config via global vars
            // humanPlayerId = initialState.players[game_logic_config.PLAYER_IDS[0]].id;
            // opponentPlayerId = initialState.players[game_logic_config.PLAYER_IDS[1]].id;
            lastRenderedActionLogCount = initialState.action_log.length;
            renderGameState(initialState, false); // false to skip animation on init
        } catch (error) {
            console.error('Error initializing game:', error);
            gameStatusMessageElem.textContent = `Error initializing game: ${error.message}. Please refresh.`;
        }
    }
    
    // Make game_logic_config accessible if needed (e.g. for PLAYER_IDS)
    // This is a bit of a hack; ideally, such config comes from server or is hardcoded consistently.
    // For now, assuming P1/P2 convention holds.
    window.game_logic_config = { PLAYER_IDS: ["P1", "P2"] }; // Simplified version for JS

    initGame();
});