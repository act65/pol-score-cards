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
    function getAttributeAbbreviation(attrName) {
        const map = {
            strength: "Str", divination: "Div", charisma: "Cha", rigor: "Rig",
            specificity: "Spe", civility: "Civ", authenticity: "Aut",
            veracity: "Ver", forthrightness: "For"
        };
        return map[attrName.toLowerCase()] || attrName.substring(0, 3);
    }

    function createCardElement(cardData, locationType) {
        const cardDiv = document.createElement('div');
        cardDiv.classList.add('card');
        cardDiv.dataset.instanceId = cardData.instance_id;
        cardDiv.dataset.name = cardData.name; // For easier identification in logs

        if (locationType === 'hand') {
            cardDiv.classList.add('hand-card');
            cardDiv.draggable = true;
        } else if (locationType === 'player-field') {
            cardDiv.classList.add('field-card', 'player-card');
        } else if (locationType === 'opponent-field') {
            cardDiv.classList.add('field-card', 'opponent-card');
        }
        
        const attributesHtml = Object.entries(cardData.attributes)
            .map(([key, value]) => `<li>${getAttributeAbbreviation(key)}: <span>${value}</span></li>`)
            .join('');
        
        // Attack target indicator div
        const attackIndicatorHtml = `<div class="attack-target-indicator" style="display: none;"></div>`;

        cardDiv.innerHTML = `
            <div class="name">${cardData.name}</div>
            <div class="party">${cardData.party}</div>
            <div class="hp">HP: ${cardData.current_hp}/${cardData.max_hp}</div>
            <ul class="attributes">${attributesHtml}</ul>
            ${attackIndicatorHtml}
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

    function addAttackAction(attackerId, targetId) {
        // Prevent multiple attacks from the same attacker
        if (playerActions.some(action => action.type === 'ATTACK' && action.attacker_instance_id === attackerId)) {
            alert("This card already has a planned attack.");
            return false;
        }
        const attackerCardElem = playerFieldElem.querySelector(`.card[data-instance-id="${attackerId}"]`);
        const targetCardElem = opponentFieldElem.querySelector(`.card[data-instance-id="${targetId}"]`);
        if (!attackerCardElem || !targetCardElem) return false;

        const attackerName = attackerCardElem.dataset.name;
        const targetName = targetCardElem.dataset.name;

        playerActions.push({ 
            type: 'ATTACK', 
            attacker_instance_id: attackerId, 
            target_instance_id: targetId,
            attacker_name: attackerName, // Store for UI
            target_name: targetName      // Store for UI
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
        
        // Animate results from action log if this render is after a turn submission
        if (animate && oldGameState && oldGameState.round_number < state.round_number || (oldGameState && oldGameState.game_phase !== "GAME_OVER" && state.game_phase === "GAME_OVER")) {
            // Only animate if round advanced or game just ended
            const newLogs = state.action_log.slice(lastRenderedActionLogCount);
            animateActionLogEvents(newLogs);
        }
        lastRenderedActionLogCount = state.action_log.length;

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


    async function animateActionLogEvents(logs) {
        submitActionsButton.disabled = true; // Disable while animating
        gameStatusMessageElem.textContent = "Resolving actions...";

        for (const log of logs) {
            // Only process logs for the current game round or if game just ended
            if (!log.startsWith(`R${currentGameState.round_number}:`) && !log.startsWith(`R${currentGameState.round_number-1}:`) && !log.includes("Game Over")) {
                if (currentGameState.game_phase === "ONGOING" && log.startsWith(`R${currentGameState.round_number-1}:`)) {
                    // This is for logs from the round that just finished processing
                } else {
                     continue;
                }
            }

            let delay = 300; // Default delay

            // Example parsing (can be made more robust)
            if (log.includes("deals") && log.includes("damage to")) {
                // R1:   Amelia Taylor deals 1364 damage to Pavel Davis. (Pavel Davis HP: 14886/16250)
                // R1:   Civility: Amelia Taylor deals 4 direct damage to Player P2 (HP: 996).
                const damageMatch = log.match(/(\w+\s*\w*)\sdeals\s(\d+)\sdamage\sto\s(Player\s\w+|[\w\s]+)\.\s\(?(?:([\w\s]+)\sHP:\s(\d+)\/(\d+))?/);
                const civilityDamageMatch = log.match(/Civility:\s([\w\s]+)\sdeals\s(\d+)\sdirect damage to Player\s(\w+)\s\(HP:\s(\d+)\)/);

                if (damageMatch) {
                    const targetName = damageMatch[3].trim();
                    const newHp = damageMatch[5];
                    const maxHp = damageMatch[6];
                    
                    const targetCardElem = Array.from(document.querySelectorAll('.card'))
                                           .find(el => el.dataset.name === targetName);
                    if (targetCardElem && newHp !== undefined) {
                        const hpDisplay = targetCardElem.querySelector('.hp');
                        if (hpDisplay) hpDisplay.textContent = `HP: ${newHp}/${maxHp}`;
                        targetCardElem.classList.add('damage-flash');
                        setTimeout(() => targetCardElem.classList.remove('damage-flash'), 500);
                        delay = 600;
                    }
                } else if (civilityDamageMatch) {
                    const targetPlayerId = civilityDamageMatch[3];
                    const newPlayerHp = civilityDamageMatch[4];
                    if (targetPlayerId === humanPlayerId) {
                        playerHpElem.textContent = newPlayerHp;
                        // Add a flash to player HP area if desired
                    } else if (targetPlayerId === opponentPlayerId) {
                        opponentHpElem.textContent = newPlayerHp;
                    }
                    delay = 600;
                }
            } else if (log.includes("has been defeated")) {
                // R1:   Pavel Davis has been defeated and moved to P2's graveyard.
                const defeatedMatch = log.match(/([\w\s]+)\shas been defeated/);
                if (defeatedMatch) {
                    const defeatedCardName = defeatedMatch[1].trim();
                    const defeatedCardElem = Array.from(document.querySelectorAll('.card'))
                                           .find(el => el.dataset.name === defeatedCardName);
                    if (defeatedCardElem) {
                        defeatedCardElem.classList.add('defeated-animation');
                        setTimeout(() => defeatedCardElem.remove(), 700); // Remove after animation
                        delay = 800;
                    }
                }
            } else if (log.includes("MISSED") || log.includes("BLOCKED")) {
                delay = 400; // Shorter delay for misses/blocks
            }
            
            // Simple log display during animation (optional)
            // gameStatusMessageElem.textContent = log.substring(log.indexOf(': ') + 2); // Show current event
            await new Promise(resolve => setTimeout(resolve, delay));
        }
        
        // Final full re-render to ensure UI is perfectly synced after animations
        renderGameState(currentGameState, false); // false to prevent re-animating
        if (currentGameState.game_phase !== "GAME_OVER") {
            submitActionsButton.disabled = false;
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
            // renderGameState will handle UI updates and animations
            renderGameState(newGameState, true); // true to trigger animations
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