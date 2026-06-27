// =========================================================================
// SMARTCOMMUTE PH - CORE APPLICATION JAVASCRIPT
// Thesis: ML-Enhanced AHP-Weighted A* Framework for Predictive Pathfinding
// =========================================================================

// --- STATE GUARD: Redirect if user skips the flow ---
function validateRouteState() {
    const pagesRequiringState = ['location.html', 'result.html'];
    const currentPage = window.location.pathname.split('/').pop();

    if (pagesRequiringState.includes(currentPage)) {
        if (!localStorage.getItem('smartCommute_selectedProfile')) {
            window.location.href = 'plan.html'; // Redirect to start if state is missing
        }
    }
}

// Call this immediately when the script loads
validateRouteState();

document.addEventListener('DOMContentLoaded', () => {
    console.log("SmartCommute PH Application Initialized.");

    // ---------------------------------------------------------------------
    // 1. GLOBAL NAVBAR SCROLL EFFECT
    // Applies a drop-shadow and solid background when scrolled down
    // ---------------------------------------------------------------------
    const navbar = document.getElementById('main-navbar');
    if (navbar) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 50) {
                navbar.classList.add('navbar-scrolled', 'shadow-sm');
            } else {
                navbar.classList.remove('navbar-scrolled', 'shadow-sm');
            }
        });
    }

    // ---------------------------------------------------------------------
    // 2. STEP 1: PROFILE SELECTION LOGIC (plan.html)
    // Handles card activation, SVG checkmark injection, and bottom bar
    // ---------------------------------------------------------------------
    const profileCards = document.querySelectorAll('.profile-card-light');
    const selectionPanel = document.getElementById('selection-panel');
    const selectedTitle = document.getElementById('selected-profile-title');
    const glowDot = document.getElementById('selected-glow-dot');

    const checkmarkSVG = `<svg viewBox="0 0 24 24" width="14" height="14" stroke="currentColor" stroke-width="3" fill="none" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`;

    if (profileCards.length > 0) {
        profileCards.forEach(card => {
            card.addEventListener('click', () => {
                // Reset all cards to inactive state
                profileCards.forEach(c => {
                    c.classList.remove('active-blue', 'active-yellow', 'active-red', 'active-green');
                    const radio = c.querySelector('.profile-radio');
                    if (radio) { 
                        radio.classList.remove('active'); 
                        radio.innerHTML = ''; 
                    }
                });

                // Apply active theme to the clicked card
                const theme = card.getAttribute('data-theme');
                if (theme) card.classList.add(`active-${theme}`);

                // Inject SVG checkmark inside the active radio circle
                const activeRadio = card.querySelector('.profile-radio');
                if (activeRadio) { 
                    activeRadio.classList.add('active'); 
                    activeRadio.innerHTML = checkmarkSVG; 
                }

                // Update bottom floating bar text & dot color
                const titleText = card.querySelector('.profile-title').innerText;
                if (selectedTitle) selectedTitle.innerText = titleText;

                if (glowDot) {
                    glowDot.className = 'glow-dot ms-2';
                    if (theme) glowDot.classList.add(`dot-${theme}`);
                }

                // Smoothly reveal continue panel
                if (selectionPanel) {
                    selectionPanel.style.display = 'block';
                    setTimeout(() => selectionPanel.classList.add('visible'), 10);
                    selectionPanel.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                }
            });
        });
    }

    // ---------------------------------------------------------------------
    // 3. STEP 1 → STEP 2: FORWARD PROFILE DATA (plan.html → locations.html)
    // ---------------------------------------------------------------------
    const continueBtn = document.getElementById('btn-continue');
    if (continueBtn) {
        continueBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const activeTitle = document.getElementById('selected-profile-title').innerText;
            const activeGlowDot = document.getElementById('selected-glow-dot');
            
            let activeTheme = 'blue';
            if (activeGlowDot.classList.contains('dot-yellow')) activeTheme = 'yellow';
            if (activeGlowDot.classList.contains('dot-red')) activeTheme = 'red';
            if (activeGlowDot.classList.contains('dot-green')) activeTheme = 'green';

            localStorage.setItem('smartCommute_selectedProfile', activeTitle);
            localStorage.setItem('smartCommute_selectedTheme', activeTheme);
            window.location.href = 'location.html';
        });
    }

    // ---------------------------------------------------------------------
    // 4. STEP 2 → STEP 3: CAPTURE CORRIDOR DATA (location.html → result.html)
    // ---------------------------------------------------------------------
    const calculateBtn = document.querySelector('.location-panel .btn-blue-pill');
    if (calculateBtn) {
        calculateBtn.addEventListener('click', (e) => {
            e.preventDefault();
            const selects = document.querySelectorAll('.location-panel select');
            if (selects.length >= 2) {
                const originText = selects[0].options[selects[0].selectedIndex].text;
                const destText = selects[1].options[selects[1].selectedIndex].text;
                const finalOrigin = selects[0].selectedIndex > 0 ? originText : "Cubao Gateway";
                const finalDest = selects[1].selectedIndex > 0 ? destText : "Pasay EDSA-Taft";
                // save the station ids (the option values) too so the result map
                // can ask the engine by id, not by display name
                const finalOriginId = selects[0].selectedIndex > 0 ? selects[0].value : "cubao";
                const finalDestId = selects[1].selectedIndex > 0 ? selects[1].value : "pasay";

                localStorage.setItem('smartCommute_routeOrigin', finalOrigin);
                localStorage.setItem('smartCommute_routeDest', finalDest);
                localStorage.setItem('smartCommute_routeOriginId', finalOriginId);
                localStorage.setItem('smartCommute_routeDestId', finalDestId);
            }
            window.location.href = 'result.html';
        });
    }

    // ---------------------------------------------------------------------
    // 5. STEP 3: RENDER DYNAMIC HEADLINE & PRIORITIZED RESULT BOX
    // Safest is Red (#ef4444), Convenient is Green (#10b981)
    // ---------------------------------------------------------------------
    // Utility: auto-fit an element's font-size so text stays on one line
    function fitTextToOneLine(elem, minPx = 48, maxPx = 104) {
        if (!elem) return;
        elem.style.whiteSpace = 'nowrap';
        elem.style.display = 'inline-block';
        let fontSize = maxPx;
        elem.style.fontSize = fontSize + 'px';

        const parent = elem.parentElement || elem;
        const maxWidth = Math.max(parent.clientWidth - 16, 50);

        // Reduce font-size until it fits or reach minimum
        while (elem.scrollWidth > maxWidth && fontSize > minPx) {
            fontSize -= 2;
            elem.style.fontSize = fontSize + 'px';
        }
    }

    // Recalculate on resize
    window.addEventListener('resize', () => {
        const summary = document.getElementById('dynamic-result-summary');
        if (summary) fitTextToOneLine(summary);
    });

    const resultTitleElem = document.getElementById('dynamic-result-title');
    const resultRouteElem = document.getElementById('dynamic-result-route');

    if (resultTitleElem && resultRouteElem) {
        const savedProfile = localStorage.getItem('smartCommute_selectedProfile') || "";
        const lowerProfile = savedProfile.toLowerCase();

        // 1. Populate Master Title & Line Break
        if (lowerProfile.includes('uncrowded')) {
            resultTitleElem.innerHTML = 'Your <span style="color: #3b82f6;">uncrowded</span><br>route home';
        } else if (lowerProfile.includes('cheap')) {
            resultTitleElem.innerHTML = 'Your <span style="color: #f59e0b;">cheapest</span><br>route home';
        } else if (lowerProfile.includes('safe')) {
            resultTitleElem.innerHTML = 'Your <span style="color: #ef4444;">safest</span><br>route home';
        } else if (lowerProfile.includes('convenient') || lowerProfile.includes('fewer')) {
            resultTitleElem.innerHTML = 'Your <span style="color: #10b981;">convenient</span><br>route home';
        } else {
            resultTitleElem.innerHTML = 'Your <span style="color: #3b82f6;">optimized</span><br>route home';
        }

        // --- NEW: Theme-Aware Gradient Logic ---
        const resultCard = document.querySelector('.result-card');
        if (resultCard) {
            // Remove any existing gradients first
            resultCard.classList.remove('gradient-blue', 'gradient-yellow', 'gradient-red', 'gradient-green');
            
            // Add the correct one based on profile
            if (lowerProfile.includes('uncrowded')) resultCard.classList.add('gradient-blue');
            else if (lowerProfile.includes('cheap')) resultCard.classList.add('gradient-yellow');
            else if (lowerProfile.includes('safe')) resultCard.classList.add('gradient-red');
            else if (lowerProfile.includes('convenient') || lowerProfile.includes('fewer')) resultCard.classList.add('gradient-green');
        }

        // 2. Populate the prioritized result details under the heading
        const detail1Label = document.getElementById('detail-1-label');
        const detail1Value = document.getElementById('detail-1-value');
        const detail2Label = document.getElementById('detail-2-label');
        const detail2Value = document.getElementById('detail-2-value');
        const detail3Label = document.getElementById('detail-3-label');
        const detail3Value = document.getElementById('detail-3-value');
        const detail4Label = document.getElementById('detail-4-label');
        const detail4Value = document.getElementById('detail-4-value');
        const summaryElem = document.getElementById('dynamic-result-summary');
        const summarySubElem = document.getElementById('dynamic-result-sub');

        if (summaryElem && summarySubElem && detail1Label && detail1Value && detail2Label && detail2Value && detail3Label && detail3Value && detail4Label && detail4Value) {
            let details = {
                title: 'Optimized',
                subtitle: 'Balanced route',
                blocks: [
                    { label: 'Time', value: '45 min' },
                    { label: 'Fare', value: '₱40' },
                    { label: 'Crowd', value: 'Moderate' },
                    { label: 'Transfers', value: '1' }
                ]
            };

            if (lowerProfile.includes('uncrowded')) {
                details = {
                    title: 'Light',
                    subtitle: 'Crowd level',
                    blocks: [
                        { label: 'Time', value: '52m' },
                        { label: 'Fare', value: '₱38' },
                        { label: 'Transfers', value: '2' },
                        { label: 'Flood', value: 'Low' }
                    ],
                    why: {
                        label: 'Why this route',
                        heading: 'Avoids heavy rush-hour traffic',
                        description: 'This route steers you through less busy options during peak travel hours, keeping your journey comfortable and clear of heavy transit crowds.',
                        color: '#3b82f6'
                    }
                };
            } else if (lowerProfile.includes('cheap')) {
                details = {
                    title: '₱28',
                    subtitle: 'Lowest Total Fare',
                    blocks: [
                        { label: 'Time', value: '61m' },
                        { label: 'Crowd', value: 'Moderate' },
                        { label: 'Transfers', value: '2' },
                        { label: 'Flood', value: 'Medium' }
                    ],
                    why: {
                        label: 'Why this route',
                        heading: 'Bypasses expensive transit rides',
                        description: 'This path uses affordable local transit options to help you save more on your daily journey compared to direct train alternatives.',
                        color: '#f59e0b'
                    }
                };
            } else if (lowerProfile.includes('safe')) {
                details = {
                    title: 'Low',
                    subtitle: 'Flood risk', // Changed from 'Flood exposure'
                    blocks: [
                        { label: 'Time', value: '47m' },
                        { label: 'Fare', value: '₱38' },
                        { label: 'Crowd', value: 'Moderate' },
                        { label: 'Transfers', value: '1' }
                    ],
                    why: {
                        label: 'Why this route',
                        heading: 'Avoids flooded streets around Aurora Boulevard', // Changed from 'segments'
                        description: 'This path keeps your trip completely safe and dry by steering clear of roads that fill with water during heavy rain downpours.', // Rephrased from thresholds/decimals and removed em dash
                        color: '#dc2626'
                    }
                };
            } else if (lowerProfile.includes('convenient') || lowerProfile.includes('fewer')) {
                details = {
                    title: '0',
                    subtitle: 'Vehicle changes', // Changed from 'Number of transfers'
                    blocks: [
                        { label: 'Time', value: '44m' },
                        { label: 'Fare', value: '₱42' },
                        { label: 'Crowd', value: 'Moderate' },
                        { label: 'Flood', value: 'High' }
                    ],
                    why: {
                        label: 'Why this route',
                        heading: 'Direct ride without changing vehicles', // Changed from 'via BGC-Makati corridor'
                        description: 'This is a single continuous ride from start to finish. You do not need to switch vehicles, saving you up to 12 minutes of waiting in line.', // Removed em dash and 'friction' talk
                        color: '#10b981'
                    }
                };
            }

            summaryElem.innerText = details.title;
            summarySubElem.innerText = details.subtitle;
            // ensure prioritized title fits on one line
            fitTextToOneLine(summaryElem, 40, 104);

            detail1Label.innerText = details.blocks[0].label;
            detail1Value.innerText = details.blocks[0].value;
            detail2Label.innerText = details.blocks[1].label;
            detail2Value.innerText = details.blocks[1].value;
            detail3Label.innerText = details.blocks[2].label;
            detail3Value.innerText = details.blocks[2].value;
            detail4Label.innerText = details.blocks[3].label;
            detail4Value.innerText = details.blocks[3].value;

            // 4. Populate the "Why This Route" section
            const whyLabel = document.getElementById('why-label');
            const whyHeading = document.getElementById('why-heading');
            const whyDescription = document.getElementById('why-description');
            const whyContainer = document.querySelector('.why-route-card');

            if (whyLabel && whyHeading && whyDescription && whyContainer && details.why) {
                whyLabel.innerText = details.why.label;
                whyHeading.innerText = details.why.heading;
                whyDescription.innerHTML = details.why.description;
                
                // light shade of the profile color, even border for visibility
                whyContainer.style.borderColor = `${details.why.color}66`;
                whyContainer.style.backgroundColor = `${details.why.color}24`;
                // lighten the label so it reads on the tinted card
                whyLabel.style.color = `color-mix(in srgb, ${details.why.color}, white 45%)`;
            }
        }

        // 3. Render Station Corridor Subtitle
        const origin = localStorage.getItem('smartCommute_routeOrigin') || "Cubao Gateway";
        const dest = localStorage.getItem('smartCommute_routeDest') || "Pasay EDSA-Taft";
        resultRouteElem.innerHTML = `${origin} &rarr; ${dest}`;
    }
    
    // ---------------------------------------------------------------------
    // 6. LOADING SCREEN LOGIC (Extended Duration)
    // ---------------------------------------------------------------------
    
    // Hide overlay only after a minimum delay
    window.addEventListener('load', () => {
        const loader = document.getElementById('loader-overlay');
        if (loader) {
            // Wait at least 800ms before fading out
            setTimeout(() => {
                loader.classList.add('loader-hidden');
            }, 400); 
        }
    });

    // Trigger loader when clicking internal links
    document.addEventListener('click', (e) => {
        const target = e.target.closest('a');
        
        // 1. Check if it's a valid link
        // 2. Ensure it's not a hash link (e.g., #map-section)
        if (target && target.href && target.href.startsWith(window.location.origin) && !target.hash) {
            const loader = document.getElementById('loader-overlay');
            if (loader) loader.classList.remove('loader-hidden');
        }
    });
});