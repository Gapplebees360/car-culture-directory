    const DEFAULT_FALLBACK_IMAGE = "assets/track-car.jpg";
    const SCENE_IMAGES = ['assets/track-car.jpg', 'assets/scene-bmw.jpg', 'assets/scene-corvette.jpg', 'assets/scene-sports.jpg', 'assets/scene-street.jpg', 'assets/scene-supercar.jpg', 'assets/hero-porsche.jpg'];

    function sceneForEvent(record) {
      const key = [record.source, record.source_id, record.title, record.category].join('|');
      const hash = Array.from(key).reduce((value, character) => ((value * 31) + character.charCodeAt(0)) >>> 0, 0);
      return SCENE_IMAGES[hash % SCENE_IMAGES.length];
    }

    // Master 50 US State List
    const ALL_US_STATES = [
      "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
      "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
      "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
      "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
      "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"
    ];

    // DOM Elements
    const eventsGrid = document.getElementById('eventsGrid');
    const searchInput = document.getElementById('searchInput');
    const stateFilter = document.getElementById('stateFilter');
    const cityFilter = document.getElementById('cityFilter');
    const categoryFilter = document.getElementById('categoryFilter');
    const eventCount = document.getElementById('eventCount');
    const dateFilter = document.getElementById('dateFilter');
    const loadMore = document.getElementById('loadMore');
    let visibleLimit = 18;

    // Populate State Filter Dropdowns
    function populateStateDropdowns(events) {
      stateFilter.innerHTML = '<option value="">All 50 states</option>';

      ALL_US_STATES.forEach(state => {
        const count = events.filter(e => e.state === state).length;
        
        const optFilter = document.createElement('option');
        optFilter.value = state;
        optFilter.textContent = count > 0 ? `${state} (${count} events)` : `${state}`;
        stateFilter.appendChild(optFilter);

      });
    }

    // Populate Dynamic Cities Dropdown based on Selected State
    function populateCityDropdown(events, selectedState = "") {
      cityFilter.innerHTML = '<option value="">All Cities</option>';

      let relevantEvents = events;
      if (selectedState) {
        relevantEvents = events.filter(e => e.state === selectedState);
      }

      const cities = [...new Set(relevantEvents.map(e => e.city).filter(Boolean))].sort();

      cities.forEach(city => {
        const option = document.createElement('option');
        option.value = city;
        option.textContent = city;
        cityFilter.appendChild(option);
      });
    }

    function safeUrl(value, fallback = '') {
      try {
        const url = new URL(value);
        return ['https:', 'http:'].includes(url.protocol) && !url.username && !url.password ? url.href : fallback;
      } catch { return fallback; }
    }

    function escapeHtml(value) {
      return String(value ?? '').replace(/[&<>"']/g, character => ({
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
      }[character]));
    }

    // Render Event Cards
    function renderEvents(filteredEvents) {
      eventsGrid.innerHTML = '';
      eventCount.textContent = `Showing ${filteredEvents.length} upcoming events`;

      if (filteredEvents.length === 0) {
        loadMore.hidden = true;
        eventsGrid.innerHTML = `
          <div class="no-results">
            <h3>No events found</h3>
            <p>${eventsData.length ? "Try adjusting your filters." : "We are rebuilding the directory with verified dates and original event sources. No verified upcoming listings are available yet."}</p>
          </div>
        `;
        return;
      }

      loadMore.hidden = filteredEvents.length <= visibleLimit;
      filteredEvents.slice(0, visibleLimit).forEach(record => {
        const event = Object.fromEntries(Object.entries(record).map(([key, value]) => [key, escapeHtml(value)]));
        const sceneImage = sceneForEvent(record);
        const sourceImage = safeUrl(record.image);
        const hasSourceImage = Boolean(sourceImage);
        const imageUrl = escapeHtml(sourceImage || sceneImage);
        const sourceUrl = escapeHtml(safeUrl(record.url));
        const hasValidUrl = Boolean(sourceUrl);
        const detailsUrl = /^\/events\/[a-f0-9]{20}\/$/.test(record.seo_path || '') ? record.seo_path : '';
        const date = new Date(record.date + 'T12:00:00');
        const month = date.toLocaleDateString('en-US', {month: 'short'});
        const day = date.getDate();

        const card = document.createElement('div');
        card.className = 'event-card';
        card.innerHTML = `
          <div class="card-image-wrapper${hasSourceImage ? ' has-artwork' : ''}">
            <span class="date-badge"><small>${month}</small>${day}</span>
            <span class="photo-note">${hasSourceImage ? 'Source artwork' : 'Scene photography'}</span>
            <span class="category-badge">${event.category || 'Car Meet'}</span>
            <img 
              src="${imageUrl}" 
              alt="${hasSourceImage ? 'Source artwork for ' + event.title : 'Automotive scene illustration'}"
              class="event-card-img${hasSourceImage ? ' is-artwork' : ''}"
              loading="lazy" decoding="async"
              onerror="this.onerror=null; this.src='${sceneImage}'; this.alt='Automotive scene illustration'; this.classList.remove('is-artwork'); this.closest('.card-image-wrapper').classList.remove('has-artwork'); this.closest('.card-image-wrapper').querySelector('.photo-note').textContent='Scene photography';"
            />
          </div>
          <div class="event-card-body">
            <h3 class="event-title">${detailsUrl ? `<a href="${detailsUrl}">${event.title}</a>` : event.title}</h3>
            <div class="meta-row">
              📅 <strong>${event.date}${event.end_date && event.end_date !== event.date ? ' – ' + event.end_date : ''}</strong> &bull; ${event.time || 'See Details'}
            </div>
            <div class="meta-row">
              📍 <strong>${event.city}, ${event.state}</strong> &bull; ${event.venue}
            </div>
            <p class="event-description">${event.description || 'No additional event details provided.'}</p>
            <div class="card-footer">
              ${event.source ? `<p class="source-note">Source: ${event.source} · Checked ${event.verified_at} UTC</p>` : ''}
              ${hasValidUrl ? `
                <a href="${sourceUrl}" target="_blank" rel="noopener noreferrer" class="event-link-btn">
                  VIEW ORIGINAL LISTING <span aria-hidden="true">↗</span>
                </a>
              ` : `
                <span class="event-link-btn" style="opacity: 0.6; cursor: default; background: transparent;">
                  Community Schedule Entry
                </span>
              `}
            </div>
          </div>
        `;
        eventsGrid.appendChild(card);
        if (globalThis.UAMCommunity) globalThis.UAMCommunity.decorateCard(card, record);
      });
    }

    // Real-Time Filter Engine
    function filterEvents() {
      const searchTerm = searchInput.value.toLowerCase().trim();
      const selectedState = stateFilter.value;
      const selectedCity = cityFilter.value;
      const selectedCategory = categoryFilter.value;
      const until = new Date();
      until.setDate(until.getDate() + Number(dateFilter.value || 0));
      const untilDate = [until.getFullYear(), String(until.getMonth()+1).padStart(2,'0'), String(until.getDate()).padStart(2,'0')].join('-');

      const filtered = eventsData.filter(event => {
        const matchesSearch = 
          !searchTerm ||
          (event.title && event.title.toLowerCase().includes(searchTerm)) ||
          (event.city && event.city.toLowerCase().includes(searchTerm)) ||
          (event.venue && event.venue.toLowerCase().includes(searchTerm)) ||
          (event.description && event.description.toLowerCase().includes(searchTerm));

        const matchesState = !selectedState || event.state === selectedState;
        const matchesCity = !selectedCity || event.city === selectedCity;
        const matchesCategory = !selectedCategory || event.category === selectedCategory;

        const matchesDate = !dateFilter.value || event.date <= untilDate;
        return matchesSearch && matchesState && matchesCity && matchesCategory && matchesDate;
      });

      renderEvents(filtered);
    }

    // Initialize Page
    document.addEventListener('DOMContentLoaded', () => {
      const now = new Date();
      const today = [now.getFullYear(), String(now.getMonth() + 1).padStart(2, '0'), String(now.getDate()).padStart(2, '0')].join('-');
      eventsData = eventsData.filter(event => /^\d{4}-\d{2}-\d{2}$/.test(event.date) && (event.end_date || event.date) >= today)
        .sort((a, b) => a.date.localeCompare(b.date));
      populateStateDropdowns(eventsData);
      const states = new Set(eventsData.map(event => event.state)).size;
      const sources = [...new Set(eventsData.map(event => event.source).filter(Boolean))];
      document.getElementById('coverageSummary').textContent = `${states} of 50 states · Sources: ${sources.join(' + ') || 'No active sources'}`;
      document.getElementById('totalEvents').textContent = eventsData.length;
      document.getElementById('totalStates').textContent = states;
      document.getElementById('totalSources').textContent = sources.length;
      populateCityDropdown(eventsData);
      renderEvents(eventsData);

      function resetPage() { visibleLimit = 18; filterEvents(); }
      searchInput.addEventListener('input', resetPage);
      
      stateFilter.addEventListener('change', () => {
        populateCityDropdown(eventsData, stateFilter.value);
        resetPage();
      });

      cityFilter.addEventListener('change', resetPage);
      dateFilter.addEventListener('change', resetPage);
      loadMore.addEventListener('click', () => { visibleLimit += 18; filterEvents(); });
      document.getElementById('resetFilters').addEventListener('click', () => {
        searchInput.value = stateFilter.value = categoryFilter.value = dateFilter.value = '';
        populateCityDropdown(eventsData);
        resetPage();
      });
      categoryFilter.addEventListener('change', resetPage);
      if (globalThis.UAMCommunity) globalThis.UAMCommunity.syncDirectory(eventsData).then(records => {
        eventsData = records.filter(event => (event.end_date || event.date) >= today).sort((a,b)=>a.date.localeCompare(b.date));
        populateStateDropdowns(eventsData); populateCityDropdown(eventsData);
        const states = new Set(eventsData.map(event=>event.state)).size;
        const sources = [...new Set(eventsData.map(event=>event.source).filter(Boolean))];
        document.getElementById('coverageSummary').textContent = `${states} of 50 states · Sources: ${sources.join(' + ')}`;
        document.getElementById('totalEvents').textContent = eventsData.length;
        document.getElementById('totalStates').textContent = states;
        document.getElementById('totalSources').textContent = sources.length;
        resetPage();
      }).catch(error => console.warn('Community event sync is unavailable:', error.message));
    });
