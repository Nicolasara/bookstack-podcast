{{-- Inline podcast player + converter for BookStack pages --}}
{{-- Requires PODCAST_SERVICE_URL env var pointing to a BookStack Podcast service --}}
@if(
    env('PODCAST_SERVICE_URL')
    && request()->fullUrlIs('*/page/*')
    && !request()->fullUrlIs('*/edit*')
    && !request()->fullUrlIs('*/revisions*')
    && !request()->fullUrlIs('*/copy*')
    && !request()->fullUrlIs('*/move*')
)

<style nonce="{{ $cspNonce ?? '' }}">
    #podcast-section { margin-top: 0.5rem; }
    #podcast-section h5 { display: flex; align-items: center; gap: 6px; }
    .podcast-episode { padding: 8px 0; border-bottom: 1px solid rgba(128,128,128,0.2); }
    .podcast-episode:last-child { border-bottom: none; }
    .podcast-badge {
        display: inline-block;
        font-size: 11px;
        padding: 1px 6px;
        border-radius: 3px;
        background: rgba(128,128,128,0.2);
        margin-bottom: 4px;
    }
    .podcast-episode audio { width: 100%; height: 32px; margin-top: 4px; }
    .podcast-btn {
        display: inline-block;
        padding: 4px 12px;
        border: 1px solid currentColor;
        border-radius: 4px;
        font-size: 12px;
        cursor: pointer;
        opacity: 0.8;
        background: none;
        color: inherit;
        margin: 2px 4px 2px 0;
    }
    .podcast-btn:hover { opacity: 1; }
    .podcast-btn[disabled] { opacity: 0.4; cursor: default; }
    .podcast-status { font-size: 12px; opacity: 0.6; }
</style>

<script nonce="{{ $cspNonce ?? '' }}">
(function() {
    var SERVICE = '{{ env("PODCAST_SERVICE_URL") }}'.replace(/\/+$/, '');
    if (!SERVICE) return;

    document.addEventListener('DOMContentLoaded', function() {
        var pageDisplay = document.querySelector('[option\\:page-display\\:page-id]');
        if (!pageDisplay) return;
        var pageId = pageDisplay.getAttribute('option:page-display:page-id');
        if (!pageId) return;

        // Find the right sidebar and inject our section
        var sidebar = document.querySelector('.actions');
        if (!sidebar) return;

        var section = document.createElement('div');
        section.id = 'podcast-section';
        section.className = 'mb-xl';
        section.innerHTML = '<h5>@icon("open-book") Audio</h5><div id="podcast-content"><span class="podcast-status">Loading...</span></div>';
        sidebar.parentNode.insertBefore(section, sidebar.nextSibling);

        var content = document.getElementById('podcast-content');

        function loadEpisodes() {
            fetch(SERVICE + '/api/page/' + pageId + '/episodes')
                .then(function(r) { return r.json(); })
                .then(function(episodes) { render(episodes); })
                .catch(function() {
                    content.innerHTML = '<span class="podcast-status">Could not reach podcast service</span>';
                });
        }

        function render(episodes) {
            var html = '';

            // Show existing episodes
            var done = episodes.filter(function(e) { return e.status === 'done'; });
            var pending = episodes.filter(function(e) { return e.status === 'processing' || e.status === 'pending'; });
            var errors = episodes.filter(function(e) { return e.status === 'error'; });

            done.forEach(function(ep) {
                html += '<div class="podcast-episode">';
                html += '<span class="podcast-badge">' + (ep.mode === 'podcast' ? 'Podcast' : ep.voice_label) + '</span>';
                if (ep.duration_seconds) {
                    var m = Math.floor(ep.duration_seconds / 60);
                    var s = Math.floor(ep.duration_seconds % 60);
                    html += ' <span class="podcast-status">' + m + ':' + (s < 10 ? '0' : '') + s + '</span>';
                }
                html += '<audio controls preload="none"><source src="' + SERVICE + '/audio/' + ep.audio_filename + '" type="audio/mpeg"></audio>';
                html += '</div>';
            });

            pending.forEach(function(ep) {
                html += '<div class="podcast-episode">';
                html += '<span class="podcast-badge">' + (ep.mode === 'podcast' ? 'Podcast' : 'Narration') + '</span>';
                html += ' <span class="podcast-status" style="opacity:1">Processing...</span>';
                html += '</div>';
            });

            errors.forEach(function(ep) {
                html += '<div class="podcast-episode">';
                html += '<span class="podcast-badge">' + (ep.mode === 'podcast' ? 'Podcast' : 'Narration') + '</span>';
                html += ' <span class="podcast-status" style="color:#c44">Error</span>';
                html += '</div>';
            });

            // Generate buttons
            var hasPodcast = episodes.some(function(e) { return e.mode === 'podcast'; });
            var hasNarration = episodes.some(function(e) { return e.mode === 'narration'; });

            html += '<div style="margin-top:8px">';
            if (!hasPodcast) {
                html += '<button class="podcast-btn" onclick="podcastConvert(\'' + pageId + '\', \'podcast\')">Generate Podcast</button>';
            }
            if (!hasNarration) {
                html += '<button class="podcast-btn" onclick="podcastConvert(\'' + pageId + '\', \'narration\')">Generate Narration</button>';
            }
            html += '</div>';

            content.innerHTML = html;

            // Poll if anything is pending
            if (pending.length > 0) {
                setTimeout(loadEpisodes, 4000);
            }
        }

        // Make convert function global so onclick works
        window.podcastConvert = function(pid, mode) {
            var form = new FormData();
            form.append('bookstack_type', 'page');
            form.append('bookstack_id', pid);
            form.append('mode', mode);
            form.append('voice', mode === 'podcast' ? 'podcast' : 'en-US-AndrewMultilingualNeural');

            fetch(SERVICE + '/convert', { method: 'POST', body: form })
                .then(function() { loadEpisodes(); })
                .catch(function() { loadEpisodes(); });
        };

        loadEpisodes();
    });
})();
</script>
@endif
