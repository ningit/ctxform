async function checkEquivalence() {
	const left = document.getElementById('left-formula')
	const right = document.getElementById('right-formula')
	const monotonic = document.getElementById('monotonic')
	const logic = document.getElementById('logic').value
	const working = document.getElementById('working')
	const message = document.getElementById('res-message')
	const panel = document.getElementById('result');

	if (!left.value || !right.value)
		return;

	working.style.display = 'initial';

	const response = await fetch('api', {
		method: 'post',
		body: JSON.stringify({
			left: left.value,
			right: right.value,
			monotonic: monotonic.checked,
			logic: logic,
		}),
		headers: { "Content-Type": "application/json", },
	});

	working.style.display = 'none';

	if (!response.ok || response.status != 200) {
		message.innerText = 'There was an internal problem';
		panel.style.display = 'none';
		return;
	}

	const content = await response.json();

	if (!content.ok) {
		message.innerText = `Error: ${content.reason}`;
		panel.style.display = 'none';
		return;
	}

	// Make results visible
	panel.style.display = '';

	if (content.equivalent) {
		message.style.color = 'green';
		message.innerText = 'The two formulas are equivalent.'
	}
	else {
		message.style.color = 'red';

		if (content.lword && content.rword)
			message.innerText = 'The two formulas are incomparable.';
		else if (content.lword)
			message.innerText = 'The second formula is covered by the first one (R → L).';
		else
			message.innerText = 'The first formula is covered by the second one (L → R).'
	}

	for (const key of ['rword', 'lword', 'lformula', 'rformula',  'cformula', 'lformula_spot', 'rformula_spot',  'cformula_spot', 'rsize', 'nrsize', 'lsize', 'nlsize', 'csize']) {
		const element = document.getElementById(key);
		element.innerHTML = content[key];
	}

	document.getElementById('lword-div').style.display = (content.lword ? 'block' : 'none');
	document.getElementById('rword-div').style.display = (content.rword ? 'block' : 'none');
	document.getElementById('spot-formulae').style.display = (logic != 'ltl' ? 'none' : 'block');
	document.getElementById('automata-info').style.display = (logic != 'ltl' ? 'none' : 'block');

	// Witnesses
	window.witnesses = content.witnesses;
	updateWitnesses();
}

function updateWitnesses()
{
    const witnessesTable = document.getElementById('witnesses')
	witnessesTable.innerHTML = ''

    // Choice of the format to show the contexts
	const format = document.getElementById('witness-format').value;

	for (const [ctx_var, repl] of Object.entries(window.witnesses)) {
		const varCell = document.createElement('td');
		const replCell = document.createElement('td');

		varCell.innerText = ctx_var;
		replCell.innerHTML = repl[format];

		const row = document.createElement('tr');
		row.appendChild(varCell);
		row.appendChild(replCell);

		witnessesTable.appendChild(row);
	}
}

function initialSetup() {
	const left = document.getElementById('left-formula');
	const right = document.getElementById('right-formula');
	const formulas = document.getElementById('formulas');

	left.addEventListener('change', checkEquivalence);
	right.addEventListener('change', checkEquivalence);
	formulas.addEventListener('change', function (event) {
		const option = event.target.selectedOptions[0].dataset;
		left.value = option.left;
		right.value = option.right;
		checkEquivalence();
	});
	formulas.selectedIndex = -1;
	formulas.addEventListener('focus', function () { formulas.selectedIndex = -1; });

	const params = new URLSearchParams(document.location.search);
	var changed = false;

	if (params.has('left')) {
		left.value = params.get('left');
		changed = true;
	}

	if (params.has('right')) {
		right.value = params.get('right');
		changed = true;
	}

	if (params.has('logic')) {
		document.getElementById('logic').value = params.get('logic');
	}

	if (params.has('mono')) {
		console.log(params.get('mono'));
		document.getElementById('monotonic').checked = params.get('mono') == 'true';
	}

	if (changed)
		checkEquivalence();
}

function copyFormulas() {
	const left = document.getElementById('left-formula');
	const right = document.getElementById('right-formula');
	navigator.clipboard.writeText(`${left.value}\n${right.value}`);
}

function copyURI() {
	const left = document.getElementById('left-formula');
	const right = document.getElementById('right-formula');
	const logic = document.getElementById('logic');
	const monotonic = document.getElementById('monotonic');

	const search = new URLSearchParams({left: left.value, right: right.value, logic: logic.value, mono: monotonic.checked});
	navigator.clipboard.writeText(`${location.origin}${location.pathname}?${search}`);
}
