// Substrate's plugin, browser side (workbench/README.md, "Client plugins"). It adds:
//   - kernel's UI as an app. Kernel sends `frame-ancestors 'none'`, so it opens in its own window rather than a tab.
//   - a dashboard widget: the system's components by lifecycle, built with mount() rather than an Alpine template,
//     to show the framework-free half of the contract.
export default function substrate(wb) {
  wb.app({id: 'kernel', title: 'Kernel (parked)', icon: 'schema', url: '/ui/', embed: 'window', order: 90});

  wb.widget({
    id: 'substrate-lifecycle', title: 'Components by lifecycle', size: 's', order: 10,
    when: (w) => Boolean(w.type('component')),
    mount(el, w) {
      const list = document.createElement('ul');
      list.className = 'wb-stat-list';
      el.append(list);
      let stale = false;
      w.api.get('component', {select: 'lifecycle'}).then((rows) => {
        if (stale) return;
        const counts = {};
        for (const r of rows) counts[r.lifecycle || 'unset'] = (counts[r.lifecycle || 'unset'] || 0) + 1;
        const entries = Object.entries(counts).sort((a, b) => b[1] - a[1]);
        if (!entries.length) list.innerHTML = '<li class="wb-faint">No components yet. Step W3 reads them from catalog-info.yaml.</li>';
        for (const [lc, n] of entries) {
          const li = document.createElement('li');
          const name = Object.assign(document.createElement('span'), {textContent: lc});
          const num = Object.assign(document.createElement('span'), {className: 'wb-stat', textContent: String(n)});
          li.append(name, num);
          list.append(li);
        }
      }).catch((e) => { list.textContent = e.message; });
      return () => { stale = true; };
    },
  });
}
