<div class="story-links">
  <a href="/story">
    <h2>The name</h2>
    <p>The Abarusura defended the Bunyoro-Kitara Kingdom in the late 19th century.</p>
    <span class="go">Read our story →</span>
  </a>
  <a href="/academy">
    <h2>The academy</h2>
    <p>5 primary and 3 secondary schools play with us.</p>
    <span class="go">Meet the academy →</span>
  </a>
  <a href="/kabalega-7s">
    <h2>Kabalega 7s</h2>
    <p>Our tournament for clubs across the region.</p>
    <span class="go">See the Kabalega 7s →</span>
  </a>
</div>

<style>
  .story-links {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 1px;
    background: var(--line);
  }

  a {
    display: block;
    padding: 26px;
    background: var(--navy);
  }

  a:hover {
    background: var(--navy2);
  }

  a:focus-visible {
    outline-offset: -4px;
  }

  h2 {
    margin: 0 0 8px;
    color: var(--red);
    font-size: 24px;
  }

  p {
    margin: 0;
    font-size: 14px;
    line-height: 1.5;
  }

  .go {
    display: block;
    margin-top: 16px;
    font-size: 14px;
    font-weight: 700;
  }

  @media (max-width: 767px) {
    .story-links {
      grid-template-columns: 1fr;
    }
  }
</style>
