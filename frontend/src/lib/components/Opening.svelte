<script lang="ts">
  import { onMount } from 'svelte'
  import { photos } from '../photos'
  import { readPaused, writePaused } from '../paused'
  import { createSlideshow, type Slideshow } from '../slideshow'

  let motion = $state(false)
  let paused = $state(false)
  let active = $state(0)
  let slideshow: Slideshow | undefined
  const storage = {
    getItem: (key: string) => sessionStorage.getItem(key),
    setItem: (key: string, value: string) => sessionStorage.setItem(key, value),
  }

  onMount(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return
    paused = readPaused(storage)
    motion = true
    slideshow = createSlideshow({
      count: photos.length,
      ms: 6000,
      onShow: (index) => { active = index },
      now: () => Date.now(),
      setTimer: (callback, delay) => window.setTimeout(callback, delay),
      clearTimer: (timer) => window.clearTimeout(timer),
    })
    if (!paused) slideshow.play()
    return () => slideshow?.pause()
  })

  function togglePaused() {
    paused = !paused
    if (paused) slideshow?.pause()
    else slideshow?.play()
    writePaused(storage, paused)
  }
</script>

<section class="opening" class:motion class:paused aria-labelledby="opening-heading">
  {#each photos as photo, index (photo.file)}
    <div
      class="photo"
      class:active={index === active}
      role="img"
      aria-label={photo.alt}
      aria-hidden={index !== active ? 'true' : undefined}
      style:background-image={`url(/images/${photo.file})`}
      style:opacity={index === active ? 1 : 0}
    ></div>
  {/each}
  <div class="text">
    <p class="kicker">HOIMA · BUNYORO-KITARA · SINCE 2025</p>
    <h1 id="opening-heading">Kabalega's warriors play rugby</h1>
    <p class="introduction">Named after the elite soldiers of Omukama Kabalega, we grow rugby across Bunyoro and give young players a place to belong.</p>
    <div class="actions">
      <a class="btn red" href="/story">Train with us</a>
      <a class="btn ghost" href="/story">Our story</a>
    </div>
  </div>
  {#if motion}
    <div class="motion-controls">
      <div class="progress" aria-hidden="true">
        {#each photos as photo, index (photo.file)}
          <div class="track">
            <div class="bar" class:active={index === active} class:complete={index < active}></div>
          </div>
        {/each}
      </div>
      <button type="button" onclick={togglePaused}>{paused ? 'Play' : 'Pause'}</button>
    </div>
  {/if}
</section>

<style>
  .opening {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    min-height: 520px;
    padding: 64px clamp(24px, 4vw, 40px);
    background-color: var(--navy);
  }

  .photo {
    position: absolute;
    inset: 0;
    z-index: -2;
    background-size: cover;
    background-position: center;
  }

  .motion .photo {
    transition: opacity 0.8s ease;
  }

  .motion .photo.active {
    animation: photo-zoom 6s linear forwards;
  }

  .motion-controls {
    display: flex;
    align-items: center;
    gap: 16px;
    margin-top: 32px;
  }

  .progress {
    display: flex;
    gap: 8px;
    width: min(240px, 60%);
  }

  .track {
    flex: 1;
    height: 4px;
    overflow: hidden;
    background: var(--mist);
  }

  .bar {
    height: 100%;
    background: var(--red);
    transform: scaleX(0);
    transform-origin: left;
  }

  .bar.complete {
    transform: scaleX(1);
  }

  .bar.active {
    animation: bar-fill 6s linear forwards;
  }

  .paused .photo.active,
  .paused .bar.active {
    animation-play-state: paused;
  }

  button {
    padding: 10px 16px;
    border: 1px solid var(--mist);
    background: var(--navy);
    color: var(--white);
    font: inherit;
    cursor: pointer;
  }

  @keyframes photo-zoom {
    from { transform: scale(1); }
    to { transform: scale(1.08); }
  }

  @keyframes bar-fill {
    from { transform: scaleX(0); }
    to { transform: scaleX(1); }
  }

  .opening::after {
    content: '';
    position: absolute;
    inset: 0;
    z-index: -1;
    background: linear-gradient(90deg, var(--navy) 0%, rgb(12 20 50 / 95%) 60%, rgb(12 20 50 / 65%) 100%);
  }

  .text {
    max-width: 520px;
  }

  .kicker {
    width: fit-content;
    margin: 0;
    background: var(--navy);
  }

  h1 {
    max-width: 10ch;
    margin: 14px 0 18px;
    font-size: clamp(2.5rem, 7.5vw, 4.5rem);
    line-height: 1.05;
  }

  .introduction {
    margin: 0;
    line-height: 1.55;
  }

  .actions {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-top: 22px;
  }

  @media (max-width: 959px) {
    .opening::after {
      background: linear-gradient(90deg, var(--navy), rgb(12 20 50 / 95%));
    }
  }
</style>
