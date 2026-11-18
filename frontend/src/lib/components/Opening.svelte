<script lang="ts">
  import { photos } from '../photos'
</script>

<section class="opening" aria-labelledby="opening-heading">
  {#each photos as photo, index (photo.file)}
    <div
      class="photo"
      role="img"
      aria-label={photo.alt}
      aria-hidden={index !== 0 ? 'true' : undefined}
      style:background-image={`url(/images/${photo.file})`}
      style:opacity={index === 0 ? 1 : 0}
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
</section>

<style>
  .opening {
    position: relative;
    isolation: isolate;
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
