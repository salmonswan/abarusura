<script lang="ts">
  import '../app.css'
  import { onNavigate } from '$app/navigation'
  import Header from '../lib/components/Header.svelte'
  import Footer from '../lib/components/Footer.svelte'
  let { children } = $props()

  onNavigate((navigation) => {
    if (!document.startViewTransition || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    return new Promise<void>((resolve) => {
      document.startViewTransition(async () => {
        resolve()
        await navigation.complete
      })
    })
  })
</script>

<a class="skip" href="#main">Skip to content</a>
<Header />
<main id="main" tabindex="-1">
  {@render children()}
</main>
<Footer />
