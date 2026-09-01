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
            window.location.href = 'profiles.html'; // Redirect to start if state is missing
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
    // 2. PROFILE DETAILS MODAL (index.html)
    // ---------------------------------------------------------------------
    const profileDetails = {
        uncrowded: {
            title: 'Uncrowded',
            iconColor: '#38bdf8',
            iconSvg: '<path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path><circle cx="12" cy="7" r="4"></circle>',
            summary: 'This profile avoids the most packed stations and corridors so you can keep a calmer buffer during rush hour, payday spikes, and crowded holiday travel.',
            points: [
                'Prioritizes less dense stations and less congested transfer points.',
                'Helps you avoid the stress of packed platforms and packed vehicle interiors.',
                'Best when you want breathing room instead of the absolute shortest trip.'
            ]
        },
        cheapest: {
            title: 'Cheapest',
            iconColor: '#fbbf24',
            iconSvg: '<line x1="12" y1="1" x2="12" y2="23"></line><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"></path>',
            summary: 'This profile looks for the lowest overall fare by mixing the best combination of jeepneys, buses, and train segments while keeping your budget in focus.',
            points: [
                'Balances fare efficiency against route convenience and transfer count.',
                'Can favor slower but cheaper legs when the cost difference is meaningful.',
                'Useful for students, commuters on tight budgets, and daily repeat riders.'
            ]
        },
        safest: {
            title: 'Safest',
            iconColor: '#f87171',
            iconSvg: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path>',
            summary: 'This profile avoids flood-prone streets and risky weather exposure, giving you the most defensible route when heavy rain or poor drainage is a concern.',
            points: [
                'Guides your route away from known waterlogged corridors and weak drainage zones.',
                'Weighs weather risk heavily during wet weather and storm-prone periods.',
                'Best when safety and predictability matter more than a slightly faster trip.'
            ]
        },
        convenient: {
            title: 'Convenient',
            iconColor: '#34d399',
            iconSvg: '<line x1="5" y1="12" x2="19" y2="12"></line><polyline points="12 5 19 12 12 19"></polyline>',
            summary: 'This profile minimizes tiring transfers and long walks so your journey feels more straightforward, especially when you are carrying bags, children, or a tight schedule.',
            points: [
                'Prefers one-seat or low-transfer trip structures over a cheaper but more complex route.',
                'Reduces friction for day-to-day commuting and time-sensitive departures.',
                'Ideal for errands, family trips, and riders who value ease over perfect optimization.'
            ]
        }
    };

    const profileModal = document.getElementById('profile-modal');
    const modalTitle = document.getElementById('profile-modal-title');
    const modalSummary = document.getElementById('profile-modal-summary');
    const modalList = document.getElementById('profile-modal-list');
    const modalIcon = document.getElementById('profile-modal-icon');

    function openProfileModal(profileKey) {
        const profile = profileDetails[profileKey];
        if (!profile || !profileModal || !modalTitle || !modalSummary || !modalList || !modalIcon) return;

        modalTitle.textContent = profile.title;
        modalSummary.textContent = profile.summary;
        modalList.innerHTML = profile.points.map(point => `<li>${point}</li>`).join('');

        const modalDialog = profileModal.querySelector('.profile-modal-dialog');
        const modalClose = profileModal.querySelector('.profile-modal-close');

        if (modalDialog) {
            modalDialog.style.background = `linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(15, 23, 42, 0.98))`;
            modalDialog.style.borderColor = `${profile.iconColor}55`;
            modalDialog.style.boxShadow = `0 24px 70px ${profile.iconColor}22`;
        }

        if (modalClose) {
            modalClose.style.background = `${profile.iconColor}18`;
            modalClose.style.color = profile.iconColor;
        }

        modalIcon.style.background = `linear-gradient(135deg, ${profile.iconColor}, rgba(15, 23, 42, 1))`;
        modalIcon.style.boxShadow = `0 12px 26px ${profile.iconColor}30`;
        modalIcon.innerHTML = `<svg viewBox="0 0 24 24" width="24" height="24" stroke="currentColor" stroke-width="2" fill="none">${profile.iconSvg}</svg>`;

        modalTitle.style.color = profile.iconColor;
        modalSummary.style.color = '#e2e8f0';
        document.documentElement.style.setProperty('--profile-accent', profile.iconColor);

        profileModal.classList.add('open');
        profileModal.setAttribute('aria-hidden', 'false');
        document.body.classList.add('modal-open');
    }

    function closeProfileModal() {
        if (!profileModal) return;
        profileModal.classList.remove('open');
        profileModal.setAttribute('aria-hidden', 'true');
        document.body.classList.remove('modal-open');
    }

    document.querySelectorAll('.profile-modal-trigger').forEach(button => {
        button.addEventListener('click', (event) => {
            event.preventDefault();
            openProfileModal(button.dataset.profile);
        });
    });

    if (profileModal) {
        profileModal.addEventListener('click', (event) => {
            const shouldClose = event.target.dataset.close === 'true' || event.target.classList.contains('profile-modal-close');
            if (shouldClose) closeProfileModal();
        });
    }

    document.addEventListener('keydown', (event) => {
        if (event.key === 'Escape' && profileModal && profileModal.classList.contains('open')) {
            closeProfileModal();
        }
    });

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
        const resultCards = document.querySelectorAll('.result-card');
        resultCards.forEach(card => {
            // Remove any existing gradients first
            card.classList.remove('gradient-blue', 'gradient-yellow', 'gradient-red', 'gradient-green');
            
            // Add the correct one based on profile
            if (lowerProfile.includes('uncrowded')) card.classList.add('gradient-blue');
            else if (lowerProfile.includes('cheap')) card.classList.add('gradient-yellow');
            else if (lowerProfile.includes('safe')) card.classList.add('gradient-red');
            else if (lowerProfile.includes('convenient') || lowerProfile.includes('fewer')) card.classList.add('gradient-green');
        });

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
                    },
                    route: 'Cubao → LRT-2 → Recto → LRT-1 → EDSA → Pasay'
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
                    },
                    route: 'Cubao → Jeepney → MRT-3 → Pasay'
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
                    },
                    route: 'Cubao → LRT-2 → MRT-3 → Pasay'
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
                    },
                    route: 'Cubao → MRT-3 (direct) → Pasay'
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

            // 5. Populate Route Breakdown (Fallback with static route)
            const breakdownContainer = document.getElementById('result-route-breakdown');
            if (breakdownContainer && details.route) {
                const segments = parseRouteSegments(details.route);
                breakdownContainer.innerHTML = segments.map((segment) => `
                    <div class="route-segment route-segment-${segment.type} ${segment.modeClass}" style="color: #f8fafc;">
                        <div class="route-segment-icon">${getRouteIconHTML(segment)}</div>
                        <div class="route-segment-info">
                            <div class="route-segment-label" style="font-size: 0.75rem; letter-spacing: 1px; text-transform: uppercase; color: #94a3b8;">${segment.label}</div>
                            <div class="route-segment-name" style="font-weight: 700; font-size: 1.05rem;">${segment.name}</div>
                            ${segment.type === 'transit' ? `<div class="route-segment-details" style="font-size: 0.85rem; color: #cbd5e1;">${segment.place || segment.destination || ''}</div>` : ''}
                        </div>
                    </div>
                `).join('');

                if (window.lucide) {
                    lucide.createIcons();
                }
            }
        }

        // Expose a function to update the breakdown with real API data
        window.renderResultRouteBreakdown = function(routeData) {
            const breakdownContainer = document.getElementById('result-route-breakdown');
            if (!breakdownContainer || !routeData) return;
            
            // Re-use buildRouteSegmentsFromRouteData from this script
            const segments = buildRouteSegmentsFromRouteData(routeData);
            if (!segments || segments.length === 0) return;

            breakdownContainer.innerHTML = segments.map((segment) => `
                <div class="route-segment route-segment-${segment.type} ${segment.modeClass}" style="color: #f8fafc;">
                    <div class="route-segment-icon">${getRouteIconHTML(segment)}</div>
                    <div class="route-segment-info">
                        <div class="route-segment-label" style="font-size: 0.75rem; letter-spacing: 1px; text-transform: uppercase; color: #94a3b8;">${segment.label}</div>
                        <div class="route-segment-name" style="font-weight: 700; font-size: 1.05rem;">${segment.name}</div>
                        ${segment.type === 'transit' ? `<div class="route-segment-details" style="font-size: 0.85rem; color: #cbd5e1;">${segment.place || segment.destination || ''}</div>` : ''}
                    </div>
                </div>
            `).join('');

            if (window.lucide) {
                lucide.createIcons();
            }
        };

        // 3. Render Station Corridor Subtitle
        const origin = localStorage.getItem('smartCommute_routeOrigin') || "Cubao Gateway";
        const dest = localStorage.getItem('smartCommute_routeDest') || "Pasay EDSA-Taft";
        resultRouteElem.innerHTML = `${origin} &rarr; ${dest}`;
    }
    
    // ---------------------------------------------------------------------
    // 6. LOADING SCREEN LOGIC (Extended Duration)
    // ---------------------------------------------------------------------
    function hideLoader() {
        const loader = document.getElementById('loader-overlay');
        if (loader) {
            loader.classList.add('loader-hidden');
            loader.style.opacity = '0';
            loader.style.pointerEvents = 'none';
            loader.style.display = 'none';
        }
    }

    function showLoader() {
        const loader = document.getElementById('loader-overlay');
        if (loader) {
            loader.style.display = 'flex';
            loader.style.opacity = '1';
            loader.style.pointerEvents = 'auto';
            loader.classList.remove('loader-hidden');
        }
    }

    // Hide overlay after a short delay, but also force it to disappear immediately
    // in case the browser skips the window load event for local/static pages.
    if (document.readyState === 'complete') {
        setTimeout(hideLoader, 500);
    } else {
        window.addEventListener('load', () => {
            setTimeout(hideLoader, 500);
        });
    }

    setTimeout(hideLoader, 1500);

    // Trigger loader only for actual page navigations, not in-page modal or anchor behavior.
    document.addEventListener('click', (e) => {
        const target = e.target.closest('a');
        if (!target || !target.href) return;

        const isSamePage = target.href.startsWith(window.location.origin + window.location.pathname) || target.href === window.location.href || target.href.startsWith(window.location.origin + '#');
        const isHashLink = target.hash || target.getAttribute('href')?.startsWith('#');
        const isModalTrigger = target.classList.contains('profile-modal-trigger');

        if (target.href.startsWith(window.location.origin) && !isSamePage && !isHashLink && !isModalTrigger) {
            const loader = document.getElementById('loader-overlay');
            if (loader) showLoader();
        }
    });
});

// =========================================================================
// ROUTE DETAILS MODAL (compare.html)
// =========================================================================
function getRouteIconHTML(segment) {
    // Get icon based on segment type and name for transit
    if (segment.type === 'start') {
        return '<i data-lucide="map-pin"></i>';
    } else if (segment.type === 'destination') {
        return '<i data-lucide="map-pin-check"></i>';
    } else if (segment.type === 'transit') {
        // Determine transit icon based on mode name
        const lowerMode = segment.name.toLowerCase();
        if (lowerMode.includes('lrt') || lowerMode.includes('mrt')) {
            return '<i data-lucide="tram-front"></i>';
        } else if (lowerMode.includes('jeepney')) {
            return '<i data-lucide="car-front"></i>';
        } else if (lowerMode.includes('bus')) {
            return '<i data-lucide="bus-front"></i>';
        }
        return '<i data-lucide="tram-front"></i>';
    } else {
        // stop type
        return '<i data-lucide="map-pin"></i>';
    }
}

function getTransitModeClass(segmentName) {
    const lowerMode = segmentName.toLowerCase();
    if (lowerMode.includes('lrt-1')) return 'mode-lrt1';
    if (lowerMode.includes('lrt-2')) return 'mode-lrt2';
    if (lowerMode.includes('mrt-3')) return 'mode-mrt3';
    if (lowerMode.includes('bus')) return 'mode-bus';
    if (lowerMode.includes('jeepney')) return 'mode-jeepney';
    return '';
}

function isTransitModeSegment(segment) {
    return ['LRT-1', 'LRT-2', 'MRT-3', 'Jeepney', 'MRT', 'LRT', 'Bus', 'Taxi'].some(mode => segment.includes(mode));
}

function getTransitPlace(segments, index) {
    const current = segments[index];
    const origin = segments[0];
    const seen = new Set([origin, current]);

    for (let i = index + 1; i < segments.length; i++) {
        const candidate = segments[i];
        if (!candidate || isTransitModeSegment(candidate)) continue;
        if (seen.has(candidate)) continue;
        seen.add(candidate);
        return candidate;
    }

    for (let i = index - 1; i >= 0; i--) {
        const candidate = segments[i];
        if (!candidate || isTransitModeSegment(candidate)) continue;
        if (seen.has(candidate)) continue;
        seen.add(candidate);
        return candidate;
    }

    return segments[segments.length - 1] || current;
}

function parseRouteSegments(routeString) {
    // Parse route strings like:
    // "Cubao → LRT-2 → Recto → LRT-1 → EDSA → Pasay"
    // "Monumento Circle → EDSA-Bus → Monumento Circle → MRT-3 → Monumento Circle → Antipolo LRT-2"
    const rawSegments = (routeString.includes('→')
        ? routeString.split('→')
        : routeString.split(/\s+-\s+/))
        .map(s => s.trim())
        .filter(Boolean);

    const cleaned = [];
    const seenNonModes = new Set();

    rawSegments.forEach((segment) => {
        const normalized = segment.trim();
        if (!normalized) return;

        if (isTransitModeSegment(normalized)) {
            cleaned.push(normalized);
            return;
        }

        const modeMatch = normalized.match(/(LRT-1|LRT-2|MRT-3|EDSA-Bus|Jeepney|Bus|MRT|LRT|Taxi)/i);
        if (modeMatch) {
            cleaned.push(normalized);
            return;
        }

        if (seenNonModes.has(normalized)) {
            return;
        }

        seenNonModes.add(normalized);
        cleaned.push(normalized);
    });

    const parsed = [];
    cleaned.forEach((segment, index) => {
        const isFirst = index === 0;
        const isLast = index === cleaned.length - 1;
        const isModeOrVehicle = isTransitModeSegment(segment) || !!segment.match(/(LRT-1|LRT-2|MRT-3|EDSA-Bus|Jeepney|Bus|MRT|LRT|Taxi)/i);

        if (isFirst) {
            parsed.push({
                type: 'start',
                name: segment,
                modeClass: '',
                label: 'Starting Point'
            });
            return;
        }

        if (isLast) {
            parsed.push({
                type: 'destination',
                name: segment,
                modeClass: '',
                label: 'Destination'
            });
            return;
        }

        if (isModeOrVehicle) {
            parsed.push({
                type: 'transit',
                name: segment,
                modeClass: getTransitModeClass(segment),
                label: 'Transit Mode',
                place: getTransitPlace(cleaned, index)
            });
            return;
        }

        parsed.push({
            type: 'stop',
            name: segment,
            modeClass: '',
            label: 'Stop'
        });
    });

    return parsed;
}

function buildRouteSegmentsFromRouteData(routeData) {
    if (!routeData || !routeData.origin || !routeData.destination) {
        return [];
    }

    const originName = routeData.origin.name || routeData.origin.id || 'Origin';
    const destinationName = routeData.destination.name || routeData.destination.id || 'Destination';
    const segments = [{
        type: 'start',
        name: originName,
        modeClass: '',
        label: 'Starting Point'
    }];

    const seenPlaces = new Set([originName, destinationName]);
    const transitLegs = Array.isArray(routeData.segments) ? routeData.segments : [];

    transitLegs.forEach((leg) => {
        const modeName = leg.mode || 'Transit';
        const placeName = leg.to_name || leg.from_name || '';
        if (!placeName || seenPlaces.has(placeName)) {
            return;
        }
        seenPlaces.add(placeName);
        segments.push({
            type: 'transit',
            name: modeName,
            modeClass: getTransitModeClass(modeName),
            label: 'Transit Mode',
            place: placeName
        });
    });

    segments.push({
        type: 'destination',
        name: destinationName,
        modeClass: '',
        label: 'Destination'
    });

    return segments;
}

function openRouteModal(routeText, profileName, routeData = null) {
    const routeModal = document.getElementById('route-details-modal');
    if (!routeModal) return;

    const modalTitle = document.getElementById('route-modal-title');
    const breakdownContainer = document.getElementById('route-breakdown');
    
    // Set title based on profile
    const profileLabels = {
        uncrowded: 'Uncrowded Route',
        cheapest: 'Cheapest Route',
        safest: 'Safest Route',
        convenient: 'Convenient Route'
    };
    
    if (modalTitle) modalTitle.textContent = profileLabels[profileName] || 'Route Details';

    // Prefer the real engine response over the static compare-card text.
    const routeDetails = routeData ? buildRouteSegmentsFromRouteData(routeData) : parseRouteSegments(routeText);
    const segments = routeDetails.length ? routeDetails : parseRouteSegments(routeText);

    breakdownContainer.innerHTML = segments.map((segment) => `
        <div class="route-segment route-segment-${segment.type} ${segment.modeClass}">
            <div class="route-segment-icon">${getRouteIconHTML(segment)}</div>
            <div class="route-segment-info">
                <div class="route-segment-label">${segment.label}</div>
                <div class="route-segment-name">${segment.name}</div>
                ${segment.type === 'transit' ? `<div class="route-segment-details">${segment.place || segment.destination || ''}</div>` : ''}
            </div>
        </div>
    `).join('');

    // Initialize lucide icons after DOM is updated
    if (window.lucide) {
        lucide.createIcons();
    }

    routeModal.classList.add('open');
    routeModal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('modal-open');
    
    // Add dynamic gradient based on profile
    const dialog = routeModal.querySelector('.route-modal-dialog');
    if (dialog) {
        dialog.classList.remove('gradient-blue', 'gradient-yellow', 'gradient-red', 'gradient-green');
        const lp = (profileName || '').toLowerCase();
        if (lp.includes('uncrowded')) dialog.classList.add('gradient-blue');
        else if (lp.includes('cheap')) dialog.classList.add('gradient-yellow');
        else if (lp.includes('safe')) dialog.classList.add('gradient-red');
        else if (lp.includes('convenient') || lp.includes('fewer')) dialog.classList.add('gradient-green');
        else dialog.classList.add('gradient-blue'); // Default fallback
    }
    
    // Render the map if the function is available
    if (window.renderModalMap) {
        window.renderModalMap(profileName);
    }
    
    // Reset scroll position to top
    const scrollContainer = breakdownContainer.closest('.custom-scrollbar') || breakdownContainer;
    if (scrollContainer) {
        scrollContainer.scrollTop = 0;
    }
}

function closeRouteModal() {
    const routeModal = document.getElementById('route-details-modal');
    if (!routeModal) return;
    
    routeModal.classList.remove('open');
    routeModal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('modal-open');
}

// Add click handlers to route elements on compare page
if (document.body.classList.contains('page-compare') || window.location.pathname.includes('compare.html')) {
    document.addEventListener('click', (e) => {
        const routeTarget = e.target.closest('.route-clickable');
        if (!routeTarget) return;

        e.preventDefault();
        const routeText = routeTarget.textContent.trim();
        const card = routeTarget.closest('.compare-card');
        const profileName = card ? card.dataset.profile : 'uncrowded';

        let routeData = null;
        if (card && card.dataset.routeData) {
            try {
                routeData = JSON.parse(card.dataset.routeData);
            } catch (error) {
                console.warn('Unable to parse route data for compare modal:', error);
            }
        }

        openRouteModal(routeText, profileName, routeData);
    });

    // Close modal on overlay click
    const routeModal = document.getElementById('route-details-modal');
    if (routeModal) {
        routeModal.addEventListener('click', (e) => {
            if (e.target.classList.contains('route-modal-overlay') || e.target.classList.contains('route-modal-close')) {
                closeRouteModal();
            }
        });
    }

    // Close modal on Escape key
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeRouteModal();
    });
}