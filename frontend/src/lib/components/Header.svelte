<script lang="ts">
  import { page } from '$app/state'
  import { isCurrent, navItems } from '../nav'
</script>

<header class="site-header">
  <a class="home" href="/">
    <img src="/images/logo.png" alt="Abarusura RFC" width="56" height="56" />
    <span class="cond" aria-hidden="true">Abarusura RFC</span>
  </a>
  <nav aria-label="Main">
    {#each navItems as { label, href }}
      <a {href} aria-current={isCurrent(page.url.pathname, href) ? 'page' : undefined}>{label}</a>
    {/each}
  </nav>
  <a class="btn red join" href="/story">Join the club</a>
</header>

<style>
  .site-header {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    padding: 10px 12px;
    background: rgb(12 20 50 / 94%);
    backdrop-filter: blur(6px);
    border-bottom: 1px solid var(--line);
  }

  .home {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-shrink: 0;
  }

  .home img {
    display: block;
    width: 50px;
    height: 50px;
    object-fit: contain;
    background: var(--white);
    border-radius: 50%;
    padding: 3px;
  }

  .home span {
    font-size: 18px;
    font-weight: 700;
  }

  nav {
    order: 3;
    flex-basis: 100%;
    display: flex;
    flex-wrap: wrap;
    gap: 8px 16px;
  }

  nav a {
    padding: 6px 2px;
    color: var(--mist);
    font-size: 14px;
    border-bottom: 2px solid transparent;
    transition: color 0.2s, border-color 0.2s;
  }

  nav a:hover, nav a:focus-visible {
    color: var(--white);
  }

  nav a[aria-current='page'] {
    color: var(--white);
    border-bottom-color: var(--red);
  }

  .join {
    padding: 11px 10px;
    font-size: 13px;
    flex-shrink: 0;
  }

  @media (min-width: 960px) {
    .site-header {
      position: sticky;
      top: 0;
      z-index: 20;
      height: var(--header-h);
      flex-wrap: nowrap;
      gap: 22px;
      padding: 10px 28px;
    }

    .home img {
      width: 56px;
      height: 56px;
    }

    .home span {
      font-size: 20px;
    }

    nav {
      order: 0;
      flex-basis: auto;
      flex-wrap: nowrap;
      margin-left: auto;
    }

    .join {
      padding: 11px 20px;
      font-size: 14px;
    }
  }
</style>
