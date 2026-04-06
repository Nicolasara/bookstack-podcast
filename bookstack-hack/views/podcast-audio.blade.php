{{-- Only on page views (not edit, revisions, etc.) --}}
@if(request()->fullUrlIs('*/page/*') && !request()->fullUrlIs('*/edit*') && !request()->fullUrlIs('*/revisions*') && !request()->fullUrlIs('*/copy*') && !request()->fullUrlIs('*/move*'))

{{-- Pre-render icons server-side so they match BookStack's style --}}
<template id="podcast-icon-listen">@icon('open-book')</template>
<template id="podcast-icon-convert">@icon('export')</template>

<script nonce="{{ $cspNonce ?? '' }}">
(function() {
    var PODCAST_URL = 'https://bookstack-podcast.stark.nicoaraujo.com';

    document.addEventListener('DOMContentLoaded', function() {
        var pageDisplay = document.querySelector('[option\\:page-display\\:page-id]');
        if (!pageDisplay) return;
        var pageId = pageDisplay.getAttribute('option:page-display:page-id');
        if (!pageId) return;

        var actions = document.querySelector('#actions .icon-list');
        if (!actions) return;

        // "Listen" button — opens podcast service with this page searched
        var listenLink = document.createElement('a');
        listenLink.href = PODCAST_URL + '/?q=' + encodeURIComponent(window.location.href);
        listenLink.target = '_blank';
        listenLink.className = 'icon-list-item';
        var listenIcon = document.getElementById('podcast-icon-listen').content.cloneNode(true);
        var listenIconSpan = document.createElement('span');
        listenIconSpan.appendChild(listenIcon);
        var listenText = document.createElement('span');
        listenText.textContent = 'Listen';
        listenLink.appendChild(listenIconSpan);
        listenLink.appendChild(listenText);
        actions.appendChild(listenLink);

        // "Convert to Podcast" button — directly triggers conversion
        var convertLink = document.createElement('a');
        convertLink.href = '#';
        convertLink.className = 'icon-list-item';
        var convertIcon = document.getElementById('podcast-icon-convert').content.cloneNode(true);
        var convertIconSpan = document.createElement('span');
        convertIconSpan.appendChild(convertIcon);
        var convertText = document.createElement('span');
        convertText.textContent = 'Convert to Podcast';
        convertLink.appendChild(convertIconSpan);
        convertLink.appendChild(convertText);

        convertLink.addEventListener('click', function(e) {
            e.preventDefault();
            convertText.textContent = 'Converting...';
            convertLink.style.opacity = '0.5';
            convertLink.style.pointerEvents = 'none';

            var form = new FormData();
            form.append('bookstack_type', 'page');
            form.append('bookstack_id', pageId);
            form.append('mode', 'podcast');
            form.append('voice', 'podcast');

            fetch(PODCAST_URL + '/convert', {
                method: 'POST',
                body: form,
                mode: 'no-cors',
            }).then(function() {
                convertText.textContent = 'Queued!';
                setTimeout(function() {
                    convertText.textContent = 'Convert to Podcast';
                    convertLink.style.opacity = '';
                    convertLink.style.pointerEvents = '';
                }, 3000);
            }).catch(function() {
                convertText.textContent = 'Failed';
                setTimeout(function() {
                    convertText.textContent = 'Convert to Podcast';
                    convertLink.style.opacity = '';
                    convertLink.style.pointerEvents = '';
                }, 3000);
            });
        });
        actions.appendChild(convertLink);
    });
})();
</script>
@endif
