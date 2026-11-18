<script lang="ts">
  import Stripe from './Stripe.svelte'

  let { kicker, title }: { kicker: string; title: string } = $props()
</script>

<div class="page-header">
  <p class="kicker">{kicker}</p>
  <h1>{title}</h1>
</div>
<Stripe />

<style>
  .page-header {
    padding: 54px clamp(16px, 4vw, 40px) 42px;
    background: linear-gradient(135deg, var(--navy), var(--navy2));
  }

  .kicker {
    margin: 0 0 12px;
  }

  h1 {
    margin: 0;
    font-size: clamp(36px, 6vw, 72px);
    font-weight: 700;
    line-height: 1.1;
  }
</style>
