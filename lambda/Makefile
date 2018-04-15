bundle: config.json handler.py ../setup.py
	rm -rf $@
	mkdir $@
	cp handler.py config.json $@/
	pip install .. -t $@/

bundle.zip: bundle
	rm -f $@
	cd bundle && zip -r ../bundle.zip .

.PHONY: clean
clean:
	rm -rf bundle bundle.zip
